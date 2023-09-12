from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import relationship
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm
from smtplib import SMTP
import os


# FLASK APP
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_KEY')
ckeditor = CKEditor(app)
Bootstrap5(app)

# LOGIN MANAGER
login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
  return User.query.get(user_id)



# CONNECT TO DB
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DB_URI', 'sqlite:///blog.db')
db = SQLAlchemy()
db.init_app(app)



# DATABASE
class User(db.Model, UserMixin):
    __tablename__ = "users"
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(1000))
    
    posts = relationship("BlogPost", back_populates="author")
    
    comments = relationship("Comment", back_populates="comment_author")

class Comment(db.Model):
    __tablename__ = "comment"
    
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    comment_author = relationship("User", back_populates="comments")
    post_id = db.Column(db.Integer, db.ForeignKey("blog_posts.id"))
    parent_post = relationship("BlogPost", back_populates="comments")
    text = db.Column(db.Text, nullable=False)

class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id = db.Column(db.Integer, primary_key=True)
    
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    
    title = db.Column(db.String(250), unique=True, nullable=False)
    subtitle = db.Column(db.String(250), nullable=False)
    date = db.Column(db.String(250), nullable=False)
    body = db.Column(db.Text, nullable=False)
    img_url = db.Column(db.String(250), nullable=False)
    
    author = relationship("User", back_populates="posts")
    
    comments = relationship("Comment", back_populates="parent_post")

with app.app_context():
    db.create_all()



# WRAPPER ADMIN ONLY
def admin_only(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.id != 1:
            return abort(403)
        return function(*args, **kwargs)        
    return decorated_function


# GRAVATAR

gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)










# ROUTE #



@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if request.method == 'POST' and form.validate_on_submit():
        email = form.email.data
        existing_user = User.query.filter_by(email=email).first()
        if not existing_user:
            new_user = User(
                        name=form.name.data,
                        email=form.email.data,
                        password=generate_password_hash(form.password.data,salt_length=8),
                    )
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            return redirect(url_for("get_all_posts"))
        else:
            flash("E-mail already registered!")
            return redirect(url_for("login"))			
    return render_template("register.html", form=form)



@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(pwhash=user.password, password=form.password.data):
            login_user(user)
            return redirect(url_for('get_all_posts'))
        else:
            flash("Invalid email or password!")
            return redirect(url_for('login'))
            
    return render_template("login.html", form=form)



@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))



@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts)




@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    form = CommentForm()
    requested_post = db.get_or_404(BlogPost, post_id)
    comments = Comment.query.filter_by(post_id=post_id)
    
    if form.validate_on_submit():
        if current_user.is_authenticated:
            new_comment = Comment(
                text = form.comment.data,
                parent_post = requested_post,
                comment_author=current_user
            )
            db.session.add(new_comment)
            db.session.commit()
            return redirect(url_for("show_post", post_id=post_id))
        else:
            flash("You have to login first!")
            return redirect(url_for("login"))
    
        
    return render_template("post.html", post=requested_post, form=form, post_comments=comments)




@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)




@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)




@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))



@app.route("/about")
def about():
    return render_template("about.html")



@app.route("/contact", methods=['GET', 'POST'])
@login_required
def contact():
    if request.method == 'POST':
        connection = SMTP("smtp.gmail.com")
        connection.starttls()
        connection.login(user=os.environ.get('CONTACT_EMAIL'), password=os.environ.get('CONTACT_PASS'))
        connection.sendmail(from_addr=os.environ.get('CONTACT_EMAIL'), to_addrs=os.environ.get('MY_EMAIL'), msg=f"By:{request.form.get('name')}  {request.form.get('email')}\n{request.form.get('message')}")
        connection.close()
        return redirect(url_for('get_all_posts'))
    return render_template("contact.html")



if __name__ == "__main__":
    app.run(debug=True, port=5002)
