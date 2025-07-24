from flask import Flask, render_template, request, redirect, session, flash, url_for, jsonify, g
import pandas as pd
import os
import datetime
from werkzeug.utils import secure_filename
import math
from flask_sqlalchemy import SQLAlchemy
import csv
from flask_migrate import Migrate
from markupsafe import Markup
from flask_login import UserMixin
import random
import re
import time
from datetime import datetime
from flask_socketio import SocketIO, emit, join_room, leave_room

# In-memory typing status: {('user1', 'user2'): timestamp}
typing_status = {}

app = Flask(__name__)
print("App started, registering routes...")

@app.template_filter('highlight_tags_and_mentions')
def highlight_tags_and_mentions(text):
    if not text:
        return ''
    text = re.sub(r'#(\w+)', r'<a href="/hashtag/\1" class="text-primary">#\1</a>', text)
    text = re.sub(r'@(\w+)', r'<a href="/user/\1" class="text-success">@\1</a>', text)
    return Markup(text)

print("highlight_tags_and_mentions filter registered")

app.secret_key = 'your_secret_key'
USERS_FILE = 'users.csv'
TRIPS_FILE = 'trips.csv'
MESSAGES_FILE = 'messages.csv'
REVIEWS_FILE = 'reviews.csv'
UPLOAD_FOLDER = 'static/profile_pics'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
NOTIFICATIONS_FILE = 'notifications.csv'
INVITATIONS_FILE = 'invitations.csv'
TRIP_GALLERY_FOLDER = 'static/images/trip_gallery'
ALLOWED_PHOTO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['TRIP_GALLERY_FOLDER'] = TRIP_GALLERY_FOLDER
os.makedirs(TRIP_GALLERY_FOLDER, exist_ok=True)
TRIP_PHOTOS_FILE = 'trip_photos.csv'
REPORTS_FILE = 'reports.csv'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///partner_web.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)



class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    bio = db.Column(db.String(300))
    interests = db.Column(db.String(300))
    profile_pic = db.Column(db.String(120))
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    profile_pic_updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    def __init__(self, username, password, bio=None, interests=None, profile_pic=None, last_seen=None, profile_pic_updated_at=None):
        self.username = username
        self.password = password
        self.bio = bio
        self.interests = interests
        self.profile_pic = profile_pic
        self.last_seen = last_seen if last_seen is not None else datetime.utcnow()
        self.profile_pic_updated_at = profile_pic_updated_at if profile_pic_updated_at is not None else datetime.utcnow()

class Trip(db.Model):
    trip_id = db.Column(db.Integer, primary_key=True)
    creator = db.Column(db.String(80), nullable=False)
    destination = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.String(50), nullable=False)
    end_date = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    preferences = db.Column(db.String(300))
    participants = db.Column(db.String(500)) # Comma-separated list of usernames
    latitude = db.Column(db.Float)  # Added for map accuracy
    longitude = db.Column(db.Float) # Added for map accuracy
    def __init__(self, trip_id, creator, destination, start_date, end_date, description=None, preferences=None, participants=None, latitude=None, longitude=None):
        self.trip_id = trip_id
        self.creator = creator
        self.destination = destination
        self.start_date = start_date
        self.end_date = end_date
        self.description = description
        self.preferences = preferences
        self.participants = participants
        self.latitude = latitude
        self.longitude = longitude

class Message(db.Model):
    message_id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(80), nullable=False)
    receiver = db.Column(db.String(80), nullable=False)
    timestamp = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Integer, default=0) # 0 = unread, 1 = read
    attachment = db.Column(db.String(255), nullable=True)  # store filename if any
    def __init__(self, message_id, sender, receiver, timestamp, content, is_read=0, attachment=None):
        self.message_id = message_id
        self.sender = sender
        self.receiver = receiver
        self.timestamp = timestamp
        self.content = content
        self.is_read = is_read
        self.attachment = attachment

class Review(db.Model):
    review_id = db.Column(db.Integer, primary_key=True)
    reviewer = db.Column(db.String(80), nullable=False)
    reviewee = db.Column(db.String(80), nullable=False)
    trip_id = db.Column(db.Integer, nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    timestamp = db.Column(db.String(50), nullable=False)
    def __init__(self, review_id, reviewer, reviewee, trip_id, rating, comment, timestamp):
        self.review_id = review_id
        self.reviewer = reviewer
        self.reviewee = reviewee
        self.trip_id = trip_id
        self.rating = rating
        self.comment = comment
        self.timestamp = timestamp

class Notification(db.Model):
    notification_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    type = db.Column(db.String(50), nullable=False) # e.g., 'trip_join', 'message', 'review'
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Integer, default=0)
    timestamp = db.Column(db.String(50), nullable=False)
    def __init__(self, notification_id, username, type, message, is_read, timestamp):
        self.notification_id = notification_id
        self.username = username
        self.type = type
        self.message = message
        self.is_read = is_read
        self.timestamp = timestamp

class Invitation(db.Model):
    invitation_id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, nullable=False)
    inviter = db.Column(db.String(80), nullable=False)
    invitee = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(50), nullable=False) # 'pending', 'accepted', 'rejected'
    timestamp = db.Column(db.String(50), nullable=False)
    def __init__(self, invitation_id, trip_id, inviter, invitee, status, timestamp):
        self.invitation_id = invitation_id
        self.trip_id = trip_id
        self.inviter = inviter
        self.invitee = invitee
        self.status = status
        self.timestamp = timestamp

class TripPhoto(db.Model):
    photo_id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(80), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.String(50), nullable=False)
    def __init__(self, photo_id, trip_id, username, filename, timestamp):
        self.photo_id = photo_id
        self.trip_id = trip_id
        self.username = username
        self.filename = filename
        self.timestamp = timestamp

class Report(db.Model):
    report_id = db.Column(db.Integer, primary_key=True)
    reporter = db.Column(db.String(80), nullable=False)
    reported = db.Column(db.String(80), nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)
    timestamp = db.Column(db.String(50), nullable=False)
    def __init__(self, report_id, reporter, reported, reason, details, timestamp):
        self.report_id = report_id
        self.reporter = reporter
        self.reported = reported
        self.reason = reason
        self.details = details
        self.timestamp = timestamp

class TripPost(db.Model):
    post_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), db.ForeignKey('user.username'), nullable=False)
    image = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    def __init__(self, username, image, caption=None, timestamp=None):
        self.username = username
        self.image = image
        self.caption = caption
        self.timestamp = timestamp if timestamp is not None else datetime.utcnow()

class TripPostLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('trip_post.post_id'), nullable=False)
    username = db.Column(db.String(80), db.ForeignKey('user.username'), nullable=False)
    def __init__(self, post_id, username):
        self.post_id = post_id
        self.username = username

class TripPostComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('trip_post.post_id'), nullable=False)
    username = db.Column(db.String(80), db.ForeignKey('user.username'), nullable=False)
    comment = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    def __init__(self, post_id, username, comment, timestamp=None):
        self.post_id = post_id
        self.username = username
        self.comment = comment
        self.timestamp = timestamp if timestamp is not None else datetime.utcnow()

class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower = db.Column(db.String(80), db.ForeignKey('user.username'), nullable=False)
    followed = db.Column(db.String(80), db.ForeignKey('user.username'), nullable=False)
    def __init__(self, follower, followed):
        self.follower = follower
        self.followed = followed

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_photo(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_PHOTO_EXTENSIONS

def allowed_post_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def register_user(username, password, bio, interests):
    if User.query.filter_by(username=username).first():
        return False  # User exists
    user = User(username, password, bio, interests)
    db.session.add(user)
    db.session.commit()
    return True

def check_login(username, password):
    user = User.query.filter_by(username=username).first()
    return user and user.password == password

def get_next_trip_id():
    last_trip = Trip.query.order_by(Trip.trip_id.desc()).first()
    return (last_trip.trip_id + 1) if last_trip else 1

def get_next_message_id():
    last_message = Message.query.order_by(Message.message_id.desc()).first()
    return (last_message.message_id + 1) if last_message else 1

def get_next_review_id():
    last_review = Review.query.order_by(Review.review_id.desc()).first()
    return (last_review.review_id + 1) if last_review else 1

def get_next_notification_id():
    last_notification = Notification.query.order_by(Notification.notification_id.desc()).first()
    return (last_notification.notification_id + 1) if last_notification else 1

def get_next_invitation_id():
    last_invitation = Invitation.query.order_by(Invitation.invitation_id.desc()).first()
    return (last_invitation.invitation_id + 1) if last_invitation else 1

def get_next_photo_id():
    last_photo = TripPhoto.query.order_by(TripPhoto.photo_id.desc()).first()
    return (last_photo.photo_id + 1) if last_photo else 1

def get_next_report_id():
    last_report = Report.query.order_by(Report.report_id.desc()).first()
    return (last_report.report_id + 1) if last_report else 1

@app.route('/', methods=['GET', 'POST'])
def home():
    if 'username' in session:
        # Handle post creation
        if request.method == 'POST':
            file = request.files.get('image')
            caption = request.form.get('caption', '')
            if file and allowed_post_file(file.filename):
                if not os.path.exists(POST_UPLOAD_FOLDER):
                    os.makedirs(POST_UPLOAD_FOLDER)
                filename = secure_filename(f"{session['username']}_{int(datetime.now().timestamp())}_{file.filename}")
                file.save(os.path.join(POST_UPLOAD_FOLDER, filename))
                post = TripPost(session['username'], filename, caption, datetime.now())
                db.session.add(post)
                db.session.commit()
                flash('Post uploaded!', 'success')
                return redirect(url_for('home'))
            else:
                flash('Invalid file type.', 'danger')

        # Prepare posts for feed
        all_posts = TripPost.query.order_by(TripPost.timestamp.desc()).all()
        your_posts = [p for p in all_posts if p.username == session['username']]
        other_posts = [p for p in all_posts if p.username != session['username']]
        for post in all_posts:
            post.like_count = TripPostLike.query.filter_by(post_id=post.post_id).count()
            post.liked_by_user = TripPostLike.query.filter_by(post_id=post.post_id, username=session['username']).first() is not None
            post.comments = TripPostComment.query.filter_by(post_id=post.post_id).order_by(TripPostComment.timestamp.asc()).all()
        if 'username' in session:
            posts_to_show = other_posts
        else:
            posts_to_show = all_posts
        return render_template('home.html', your_posts=your_posts, posts_to_show=posts_to_show, all_posts=all_posts, active_page='home', get_avatar_url=get_avatar_url)
    else:
        # For guests, just show the feed
        all_posts = TripPost.query.order_by(TripPost.timestamp.desc()).all()
        for post in all_posts:
            post.like_count = TripPostLike.query.filter_by(post_id=post.post_id).count()
            post.liked_by_user = False
            post.comments = TripPostComment.query.filter_by(post_id=post.post_id).order_by(TripPostComment.timestamp.asc()).all()
        return render_template('home.html', all_posts=all_posts, get_avatar_url=get_avatar_url)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        bio = request.form.get('bio', '')
        interests = request.form.get('interests', '')
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
        else:
            user = User(username, password, bio, interests)
            db.session.add(user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if check_login(username, password):
            session['username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

@app.route('/profile')
def profile():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = User.query.filter_by(username=session['username']).first()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('logout'))

    # Calculate badges
    badges = []
    trips_df = Trip.query.filter(Trip.participants.like(f"%{user.username}%")).all()
    if len(trips_df) >= 1:
        badges.append('First Trip')
    if len(trips_df) >= 5:
        badges.append('Explorer')
    reviews_df = Review.query.filter_by(reviewee=user.username).all()
    if len(reviews_df) >= 3:
        badges.append('Top Reviewer')
    photos_df = TripPhoto.query.filter_by(username=user.username).all()
    if len(photos_df) >= 1:
        badges.append('Photographer')

    # Get reviews for this user
    reviews = []
    reviews_df = Review.query.filter_by(reviewee=user.username).all()
    for review in reviews_df:
        reviews.append(review.__dict__)

    # Get posts for this user
    posts = TripPost.query.filter_by(username=user.username).order_by(TripPost.timestamp.desc()).all()

    # Get followers and following lists
    followers = [f.follower for f in Follow.query.filter_by(followed=user.username).all()]
    following = [f.followed for f in Follow.query.filter_by(follower=user.username).all()]

    return render_template('profile.html', user=user.__dict__, reviews=reviews, badges=badges, posts=posts, followers=followers, following=following)

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = User.query.filter_by(username=session['username']).first()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('logout'))
    if request.method == 'POST':
        print(f"[DEBUG] request.files: {request.files}")
        print(f"[DEBUG] request.form: {request.form}")
        bio = request.form.get('bio', '')
        interests = request.form.get('interests', '')
        file = request.files.get('profile_pic')
        print(f"[DEBUG] Received file: {file.filename if file else None}")
        if file and file.filename and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = secure_filename(f"{user.username}.{ext}")
            print(f"[DEBUG] New profile pic filename: {filename}")
            # Delete old profile pics with different extensions
            for old_ext in ['jpg', 'jpeg', 'png', 'gif']:
                old_filename = f"{user.username}.{old_ext}"
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
                if old_ext != ext and os.path.exists(old_path):
                    os.remove(old_path)
                    print(f"[DEBUG] Deleted old profile pic: {old_path}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            print(f"[DEBUG] Saved new profile pic: {filename}")
            user.profile_pic = filename
            user.profile_pic_updated_at = datetime.utcnow()
            print(f"[DEBUG] Updated user.profile_pic: {user.profile_pic}")
            print(f"[DEBUG] Updated user.profile_pic_updated_at: {user.profile_pic_updated_at}")
        user.bio = bio
        user.interests = interests
        db.session.commit()
        print(f"[DEBUG] Profile updated for user: {user.username}")
        flash('Profile updated!', 'success')
        return redirect(url_for('profile'))
    return render_template('edit_profile.html', user=user, random=random.random)

@app.route('/create_trip', methods=['GET', 'POST'])
def create_trip():
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        trip_id = get_next_trip_id()
        creator = session['username']
        destination = request.form['destination']
        start_date = request.form['start_date']
        end_date = request.form['end_date']
        description = request.form['description']
        preferences = request.form['preferences']
        participants = creator  # creator is the first participant

        trip = Trip(trip_id, creator, destination, start_date, end_date, description, preferences, participants)
        db.session.add(trip)
        db.session.commit()
        flash('Trip created successfully!', 'success')
        return redirect(url_for('list_trips'))
    return render_template('create_trip.html')

@app.route('/trips')
def list_trips():
    trips_query = Trip.query
    # Filtering
    destination = request.args.get('destination', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    preferences = request.args.get('preferences', '')
    if destination:
        trips_query = trips_query.filter(Trip.destination.ilike(f"%{destination}%"))
    if start_date:
        trips_query = trips_query.filter(Trip.start_date >= start_date)
    if end_date:
        trips_query = trips_query.filter(Trip.end_date <= end_date)
    if preferences:
        trips_query = trips_query.filter(Trip.preferences.ilike(f"%{preferences}%"))
    trips = [trip.__dict__ for trip in trips_query.all()]
    return render_template('list_trips.html', trips=trips)

@app.route('/join_trip/<int:trip_id>', methods=['POST'])
def join_trip(trip_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    trip = Trip.query.filter_by(trip_id=trip_id).first()
    if not trip:
        flash('Trip not found.', 'danger')
        return redirect(url_for('list_trips'))

    participants_list = trip.participants.split(',')
    username = session['username']
    if username not in participants_list:
        trip.participants = participants_list + ',' + username
        db.session.commit()
        # Add notification for trip creator
        creator = trip.creator
        if creator != username:
            notification_id = get_next_notification_id()
            message = f"{username} joined your trip to {trip.destination}."
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            notification = Notification(notification_id, creator, 'trip_join', message, 0, timestamp)
            db.session.add(notification)
            db.session.commit()
        flash('You have joined the trip!', 'success')
    return redirect(url_for('list_trips'))

@app.route('/send_message/<receiver>', methods=['GET', 'POST'])
def send_message(receiver):
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        message_id = get_next_message_id()
        sender = session['username']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        content = request.form['content']
        message = Message(message_id, sender, receiver, timestamp, content)
        db.session.add(message)
        db.session.commit()
        flash('Message sent!', 'success')
        return redirect(url_for('inbox'))
    return render_template('send_message.html', receiver=receiver)

@app.route('/inbox')
def inbox():
    if 'username' not in session:
        return redirect(url_for('login'))
    messages = []
    messages_df = Message.query.filter_by(receiver=session['username']).order_by(Message.timestamp.desc()).all()
    for msg in messages_df:
        messages.append(msg.__dict__)
    # Mark as read
    for msg in messages_df:
        if msg.is_read == 0:
            msg.is_read = 1
            db.session.commit()
    return render_template('inbox.html', messages=messages)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        # You can add logic here to send an email or save the message
        flash('Thank you for contacting us! We will get back to you soon.', 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/review/<reviewee>/<int:trip_id>', methods=['GET', 'POST'])
def review_user(reviewee, trip_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        review_id = get_next_review_id()
        reviewer = session['username']
        rating = int(request.form['rating'])
        comment = request.form['comment']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        review = Review(review_id, reviewer, reviewee, trip_id, rating, comment, timestamp)
        db.session.add(review)
        db.session.commit()
        flash('Review submitted!', 'success')
        return redirect(url_for('profile'))
    return render_template('review.html', reviewee=reviewee, trip_id=trip_id)

def model_to_dict(obj):
    return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}

@app.route('/notifications')
def notifications():
    if 'username' not in session:
        return redirect(url_for('login'))
    notifications = []
    notifications_df = Notification.query.filter_by(username=session['username']).order_by(Notification.timestamp.desc()).all()
    for notif in notifications_df:
        notif_dict = model_to_dict(notif)
        # Attach inviter, invitation_id, status, and trip details for trip_invite (any status)
        if notif.type == 'trip_invite':
            # Try to extract inviter from the message if not present
            inviter = notif_dict.get('inviter')
            if not inviter:
                inviter = notif.message.split(' ')[0]
            # Find the most recent invitation for this notification, regardless of status
            invitation = Invitation.query.filter_by(
                invitee=session['username'],
                inviter=inviter
            ).order_by(Invitation.timestamp.desc()).first()
            if invitation:
                notif_dict['inviter'] = invitation.inviter
                notif_dict['invitation_id'] = invitation.invitation_id
                notif_dict['invite_status'] = invitation.status
                trip = Trip.query.filter_by(trip_id=invitation.trip_id).first()
                if trip:
                    notif_dict['trip_destination'] = trip.destination
                    notif_dict['trip_start'] = trip.start_date
                    notif_dict['trip_end'] = trip.end_date
        notifications.append(notif_dict)
    # Mark as read
    for notif in notifications_df:
        if notif.is_read == 0:
            notif.is_read = 1
            db.session.commit()
    # Get pending invitations for this user
    invitations = []
    invitations_df = Invitation.query.filter_by(invitee=session['username']).filter_by(status='pending').all()
    for inv in invitations_df:
        invitations.append(model_to_dict(inv))
    return render_template('notifications.html', notifications=notifications, invitations=invitations, get_avatar_url=get_avatar_url)

@app.route('/invite/<int:trip_id>/<invitee>', methods=['POST'])
def invite_user(trip_id, invitee):
    if 'username' not in session:
        return redirect(url_for('login'))
    trip = Trip.query.filter_by(trip_id=trip_id).first()
    if not trip or trip.creator != session['username']:
        flash('Only the trip creator can invite users.', 'danger')
        return redirect(url_for('invite_page', trip_id=trip_id))
    inviter = session['username']
    # Check for existing invitation in last 24 hours
    from datetime import datetime, timedelta
    recent_invitation = Invitation.query.filter_by(trip_id=trip_id, inviter=inviter, invitee=invitee).order_by(Invitation.timestamp.desc()).first()
    if recent_invitation:
        try:
            last_time = datetime.strptime(recent_invitation.timestamp, '%Y-%m-%d %H:%M:%S')
        except Exception:
            last_time = datetime.now() - timedelta(days=1, seconds=1)  # fallback: allow
        if (datetime.now() - last_time).total_seconds() < 86400:
            flash('You have already invited this user to this trip in the last 24 hours.', 'warning')
            return redirect(url_for('invite_page', trip_id=trip_id))
    invitation_id = get_next_invitation_id()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status = 'pending'
    invitation = Invitation(invitation_id, trip_id, inviter, invitee, status, timestamp)
    db.session.add(invitation)
    db.session.commit()
    # --- Add notification for invitee ---
    notification_id = get_next_notification_id()
    message = f"{inviter} invited you to join a trip to {trip.destination}."
    notification = Notification(notification_id, invitee, 'trip_invite', message, 0, timestamp)
    db.session.add(notification)
    db.session.commit()
    flash(f'Invitation sent to {invitee}!', 'success')
    return redirect(url_for('list_trips'))

@app.route('/invitations', methods=['GET', 'POST'])
def invitations():
    if 'username' not in session:
        return redirect(url_for('login'))
    invitations = []
    invitations_df = Invitation.query.filter_by(invitee=session['username']).filter_by(status='pending').all()
    for inv in invitations_df:
        invitations.append(inv.__dict__)
    return render_template('invitations.html', invitations=invitations)

@app.route('/respond_invitation/<int:invitation_id>/<response>', methods=['POST'])
def respond_invitation(invitation_id, response):
    invitation = Invitation.query.filter_by(invitation_id=invitation_id).first()
    if not invitation:
        flash('Invitation not found.', 'danger')
        return redirect(url_for('invitations'))

    invitation.status = response
    db.session.commit()
    # Notify inviter
    from datetime import datetime
    notification_id = get_next_notification_id()
    trip = Trip.query.filter_by(trip_id=invitation.trip_id).first()
    if response == 'accepted':
        message = f"{invitation.invitee} accepted your trip invitation to {trip.destination}."
    else:
        message = f"{invitation.invitee} rejected your trip invitation to {trip.destination}."
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    notification = Notification(notification_id, invitation.inviter, 'trip_invite_response', message, 0, timestamp)
    db.session.add(notification)
    db.session.commit()
    if response == 'accepted':
        # Optionally, add user to trip participants
        trip_id = invitation.trip_id
        if trip:
            participants_list = trip.participants.split(',')
            if session['username'] not in participants_list:
                participants_list.append(session['username'])
                trip.participants = ','.join(participants_list)
                db.session.commit()
        flash('Invitation response recorded.', 'success')
    else:
        flash('Invitation response recorded.', 'success')
    return redirect(url_for('invitations'))

@app.route('/trip/<int:trip_id>')
def trip_details(trip_id):
    trip = Trip.query.filter_by(trip_id=trip_id).first()
    if not trip:
        return "Trip not found", 404
    return render_template('trip_details.html', trip=trip.__dict__)

@app.route('/trip/<int:trip_id>/gallery', methods=['GET', 'POST'])
def trip_gallery(trip_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    photos = []
    photos_df = TripPhoto.query.filter_by(trip_id=trip_id).all()
    for photo in photos_df:
        photos.append(photo.__dict__)
    if request.method == 'POST':
        file = request.files.get('photo')
        if file and allowed_photo(file.filename):
            filename = secure_filename(f"{trip_id}_{session['username']}_{file.filename}")
            photo_id = get_next_photo_id()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            photo = TripPhoto(photo_id, trip_id, session['username'], filename, timestamp)
            db.session.add(photo)
            db.session.commit()
            flash('Photo uploaded!', 'success')
            return redirect(url_for('trip_gallery', trip_id=trip_id))
        else:
            flash('Invalid file type.', 'danger')
    return render_template('trip_gallery.html', trip_id=trip_id, photos=photos)

@app.route('/trip/<int:trip_id>/invite', methods=['GET', 'POST'])
def invite_page(trip_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    trip = Trip.query.filter_by(trip_id=trip_id).first()
    if not trip:
        return "Trip not found", 404
    participants = trip.participants.split(',')
    # Exclude participants and the creator from the invite list
    users_df = User.query.filter(~User.username.in_(participants)).all()
    from datetime import datetime, timedelta
    invite_candidates = []
    for user in users_df:
        # Check for recent invite from current user to this user for this trip
        recent_invite = Invitation.query.filter_by(trip_id=trip_id, inviter=session['username'], invitee=user.username).order_by(Invitation.timestamp.desc()).first()
        cooldown = None
        if recent_invite:
            try:
                last_time = datetime.strptime(recent_invite.timestamp, '%Y-%m-%d %H:%M:%S')
                seconds_left = 86400 - (datetime.now() - last_time).total_seconds()
                if seconds_left > 0:
                    cooldown = int(seconds_left)
            except Exception:
                cooldown = None
        user_dict = user.__dict__.copy()
        user_dict['invite_cooldown'] = cooldown
        invite_candidates.append(user_dict)
    return render_template('invite_page.html', trip=trip.__dict__, invite_candidates=invite_candidates, current_user=session['username'])

@app.route('/verify/<username>/<token>')
def verify_email(username, token):
    user = User.query.filter_by(username=username).first()
    if user and user.verify_token == token:
        user.is_verified = 1
        user.verify_token = ''
        db.session.commit()
        flash('Email verified! You can now log in.', 'success')
    else:
        flash('Invalid or expired verification link.', 'danger')
    return redirect(url_for('login'))

@app.route('/users')
def list_users():
    users_query = User.query
    username = request.args.get('username', '')
    interests = request.args.get('interests', '')
    bio = request.args.get('bio', '')
    if username:
        users_query = users_query.filter(User.username.ilike(f"%{username}%"))
    if interests:
        users_query = users_query.filter(User.interests.ilike(f"%{interests}%"))
    if bio:
        users_query = users_query.filter(User.bio.ilike(f"%{bio}%"))
    users = [user.__dict__ for user in users_query.all()]
    return render_template('list_users.html', users=users)

@app.route('/user/<username>')
def view_profile(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('home'))
    posts = TripPost.query.filter_by(username=username).order_by(TripPost.timestamp.desc()).all()
    followers = [f.follower for f in Follow.query.filter_by(followed=username).all()]
    following = [f.followed for f in Follow.query.filter_by(follower=username).all()]
    is_following = False
    if 'username' in session and session['username'] != username:
        is_following = Follow.query.filter_by(follower=session['username'], followed=username).first() is not None
    return render_template('profile.html', user=user, posts=posts, followers=followers, following=following, is_following=is_following)

@app.route('/report/<reported>', methods=['GET', 'POST'])
def report_user(reported):
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        report_id = get_next_report_id()
        reporter = session['username']
        reason = request.form['reason']
        details = request.form.get('details', '')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        report = Report(report_id, reporter, reported, reason, details, timestamp)
        db.session.add(report)
        db.session.commit()
        flash('Report submitted. Thank you for helping keep the community safe.', 'success')
        return redirect(url_for('home'))
    return render_template('report_user.html', reported=reported)

@app.route('/edit_trip/<int:trip_id>', methods=['GET', 'POST'])
def edit_trip(trip_id):
    trip = Trip.query.filter_by(trip_id=trip_id).first()
    if not trip or trip.creator != session.get('username'):
        flash('Unauthorized or trip not found.', 'danger')
        return redirect(url_for('list_trips'))
    if request.method == 'POST':
        trip.destination = request.form['destination']
        trip.start_date = request.form['start_date']
        trip.end_date = request.form['end_date']
        trip.description = request.form['description']
        trip.preferences = request.form['preferences']
        db.session.commit()
        flash('Trip updated!', 'success')
        return redirect(url_for('list_trips'))
    return render_template('edit_trip.html', trip=trip)

@app.route('/delete_trip/<int:trip_id>', methods=['POST'])
def delete_trip(trip_id):
    trip = Trip.query.filter_by(trip_id=trip_id).first()
    if not trip or trip.creator != session.get('username'):
        flash('Unauthorized or trip not found.', 'danger')
        return redirect(url_for('list_trips'))
    db.session.delete(trip)
    db.session.commit()
    flash('Trip deleted.', 'success')
    return redirect(url_for('list_trips'))

import os
from werkzeug.utils import secure_filename

POST_UPLOAD_FOLDER = 'static/trip_posts'

@app.route('/trip_posts', methods=['GET', 'POST'])
def trip_posts():
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        file = request.files.get('image')
        caption = request.form.get('caption', '')
        if file and allowed_post_file(file.filename):
            if not os.path.exists(POST_UPLOAD_FOLDER):
                os.makedirs(POST_UPLOAD_FOLDER)
            filename = secure_filename(f"{session['username']}_{int(datetime.now().timestamp())}_{file.filename}")
            file.save(os.path.join(POST_UPLOAD_FOLDER, filename))
            post = TripPost(session['username'], filename, caption, datetime.now())
            db.session.add(post)
            db.session.commit()
            flash('Post uploaded!', 'success')
            return redirect(url_for('trip_posts'))
        else:
            flash('Invalid file type.', 'danger')
    posts = TripPost.query.order_by(TripPost.timestamp.desc()).all()
    for post in posts:
        post.like_count = TripPostLike.query.filter_by(post_id=post.post_id).count()
        post.liked_by_user = False
        if 'username' in session:
            post.liked_by_user = TripPostLike.query.filter_by(post_id=post.post_id, username=session['username']).first() is not None
        post.comments = TripPostComment.query.filter_by(post_id=post.post_id).order_by(TripPostComment.timestamp.asc()).all()
    return render_template('trip_posts.html', posts=posts, get_avatar_url=get_avatar_url)

@app.route('/post/<int:post_id>')
def post_view(post_id):
    post = TripPost.query.get_or_404(post_id)
    like_count = TripPostLike.query.filter_by(post_id=post_id).count()
    liked_by_user = False
    if 'username' in session:
        liked_by_user = TripPostLike.query.filter_by(post_id=post_id, username=session['username']).first() is not None
    comments = TripPostComment.query.filter_by(post_id=post_id).order_by(TripPostComment.timestamp.asc()).all()
    return render_template('post_view.html', post=post, like_count=like_count, liked_by_user=liked_by_user, comments=comments)

@app.route('/trip_post/<int:post_id>/like', methods=['POST'])
def like_trip_post(post_id):
    if 'username' not in session:
        return jsonify({'success': False}), 401
    like = TripPostLike.query.filter_by(post_id=post_id, username=session['username']).first()
    post = TripPost.query.get(post_id)
    if like:
        db.session.delete(like)
        db.session.commit()
        return jsonify({'liked': False, 'count': TripPostLike.query.filter_by(post_id=post_id).count()})
    else:
        new_like = TripPostLike(post_id, session['username'])
        db.session.add(new_like)
        db.session.commit()
        # --- Notification for like ---
        if post and post.username != session['username']:
            notification_id = get_next_notification_id()
            message = f"{session['username']} liked your post."
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            notification = Notification(notification_id, post.username, 'like', message, 0, timestamp)
            db.session.add(notification)
            db.session.commit()
        return jsonify({'liked': True, 'count': TripPostLike.query.filter_by(post_id=post_id).count()})

@app.route('/trip_post/<int:post_id>/comment', methods=['POST'])
def comment_trip_post(post_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    comment_text = request.form.get('comment')
    post = TripPost.query.get(post_id)
    if comment_text:
        comment = TripPostComment(post_id, session['username'], comment_text, datetime.now())
        db.session.add(comment)
        db.session.commit()
        # --- Notification for comment ---
        if post and post.username != session['username']:
            notification_id = get_next_notification_id()
            message = f"{session['username']} commented on your post."
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            notification = Notification(notification_id, post.username, 'comment', message, 0, timestamp)
            db.session.add(notification)
            db.session.commit()
    return redirect(url_for('trip_posts'))

@app.route('/delete_post/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    post = TripPost.query.get(post_id)
    if post and post.username == session['username']:
        # Delete the image file from disk
        image_path = os.path.join('static/trip_posts', post.image)
        if os.path.exists(image_path):
            os.remove(image_path)
        db.session.delete(post)
        db.session.commit()
        flash('Post deleted!', 'success')
    else:
        flash('Unauthorized or post not found.', 'danger')
    return redirect(url_for('profile'))

@app.route('/edit_post/<int:post_id>', methods=['GET', 'POST'])
def edit_post(post_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    post = TripPost.query.get(post_id)
    if not post or post.username != session['username']:
        flash('Unauthorized or post not found.', 'danger')
        return redirect(url_for('profile'))
    if request.method == 'POST':
        post.caption = request.form.get('caption', '')
        db.session.commit()
        flash('Post updated!', 'success')
        return redirect(url_for('profile'))
    return render_template('edit_post.html', post=post)

def get_all_users_except(current_user):
    users = []
    with open('users.csv', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['username'] != current_user:
                users.append(row['username'])
    return users

def get_display_name(username):
    with open('users.csv', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['username'] == username:
                return row.get('display_name', username) or username
    return username

def get_avatar_url(username):
    user = User.query.filter_by(username=username).first()
    if user and user.profile_pic:
        return url_for('static', filename=f'profile_pics/{user.profile_pic}')
    # Fallback to default avatar
    return url_for('static', filename='default_avatar.png')

def get_last_message_and_unread(current_user, other_user):
    last_msg = ""
    unread = False
    last_time = ""
    with open('messages.csv', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Check both directions
            if (row['sender'] == current_user and row['receiver'] == other_user) or \
               (row['sender'] == other_user and row['receiver'] == current_user):
                last_msg = row['content']
                last_time = row.get('timestamp', '')
                # Mark as unread if the last message is from other_user and not marked as read
                if row['receiver'] == current_user and row['sender'] == other_user and row.get('read', '0') == '0':
                    unread = True
    if last_time:
        last_msg = f"{last_msg} · {last_time}"
    return last_msg, unread

@app.route('/messages')
def messages():
    if 'username' not in session:
        return redirect(url_for('login'))
    current_user = session['username']
    # Find all users who have a conversation (sent or received messages) with current_user
    user_set = set()
    all_msgs = Message.query.filter((Message.sender == current_user) | (Message.receiver == current_user)).all()
    for msg in all_msgs:
        if msg.sender != current_user:
            user_set.add(msg.sender)
        if msg.receiver != current_user:
            user_set.add(msg.receiver)
    conversations = []
    now = datetime.utcnow()
    for user in user_set:
        last_msg, unread = get_last_message_and_unread(current_user, user)
        user_obj = User.query.filter_by(username=user).first()
        is_online = False
        if user_obj and user_obj.last_seen:
            is_online = (now - user_obj.last_seen).total_seconds() < 120  # 2 minutes
        conversations.append({
            'username': user,
            'avatar_url': get_avatar_url(user),
            'last_message': last_msg,
            'unread': unread,
            'is_online': is_online
        })
    # Sort by unread and last message time
    conversations.sort(key=lambda x: (not x['unread'], x['last_message']), reverse=True)
    return render_template('dm_layout.html', conversations=conversations, active_user=None, get_avatar_url=get_avatar_url)

@app.route('/new_message')
def new_message():
    if 'username' not in session:
        return redirect(url_for('login'))
    current_user = session['username']
    # Find users with whom there is NO conversation
    user_set = set()
    all_msgs = Message.query.filter((Message.sender == current_user) | (Message.receiver == current_user)).all()
    for msg in all_msgs:
        if msg.sender != current_user:
            user_set.add(msg.sender)
        if msg.receiver != current_user:
            user_set.add(msg.receiver)
    # All users except current and those in user_set
    all_users = [u.username for u in User.query.all() if u.username != current_user and u.username not in user_set]
    return render_template('new_message.html', users=all_users)

@app.route('/chat/<username>', methods=['GET', 'POST'])
def chat(username):
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        content = request.form['content']
        file = request.files.get('attachment')
        filename = None
        if file and file.filename:
            if not os.path.exists(UPLOAD_FOLDER):
                os.makedirs(UPLOAD_FOLDER)
            filename = secure_filename(f"{session['username']}_{int(datetime.utcnow().timestamp())}_{file.filename}")
            file.save(os.path.join(UPLOAD_FOLDER, filename))
        message_id = get_next_message_id()
        message = Message(
            message_id,
            session['username'],
            username,
            datetime.utcnow(),
            content,
            0,
            filename
        )
        db.session.add(message)
        db.session.commit()
        return redirect(url_for('chat', username=username))
    # Get all messages between the two users
    messages = Message.query.filter(
        ((Message.sender == session['username']) & (Message.receiver == username)) |
        ((Message.sender == username) & (Message.receiver == session['username']))
    ).order_by(Message.timestamp).all()

    # Mark all messages from 'username' to current user as read
    for msg in messages:
        if msg.sender == username and msg.receiver == session['username'] and msg.is_read == 0:
            msg.is_read = 1
    db.session.commit()

    other_user_obj = User.query.filter_by(username=username).first()
    is_online = False
    last_seen = None
    if other_user_obj and other_user_obj.last_seen:
        now = datetime.utcnow()
        last_seen = other_user_obj.last_seen
        is_online = (now - last_seen).total_seconds() < 120  # 2 minutes

    # Prepare conversations for sidebar
    current_user = session['username']
    conversations = []
    now = datetime.utcnow()
    for user in get_all_users_except(current_user):
        last_msg, unread = get_last_message_and_unread(current_user, user)
        user_obj = User.query.filter_by(username=user).first()
        is_online_sidebar = False
        if user_obj and user_obj.last_seen:
            is_online_sidebar = (now - user_obj.last_seen).total_seconds() < 120
        conversations.append({
            'username': user,
            'display_name': get_display_name(user),
            'avatar_url': get_avatar_url(user),
            'last_message': last_msg,
            'unread': unread,
            'is_online': is_online_sidebar
        })
    conversations.sort(key=lambda x: (not x['unread'], x['last_message']), reverse=True)

    return render_template(
        'dm_layout.html',
        conversations=conversations,
        active_user=username,
        messages=messages,
        other_user=username,
        is_online=is_online,
        last_seen=last_seen,
        get_avatar_url=get_avatar_url
    )

@app.route('/chat/<username>/messages')
def get_chat_messages(username):
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    # Get all messages between the two users
    messages = Message.query.filter(
        ((Message.sender == session['username']) & (Message.receiver == username)) |
        ((Message.sender == username) & (Message.receiver == session['username']))
    ).order_by(Message.timestamp).all()
    # Mark as read (optional, or keep in main chat route)
    for msg in messages:
        if msg.sender == username and msg.receiver == session['username'] and msg.is_read == 0:
            msg.is_read = 1
    db.session.commit()
    # Return messages as JSON
    return jsonify([
        {
            'sender': msg.sender,
            'content': msg.content,
            'timestamp': str(msg.timestamp),
            'attachment': msg.attachment
        } for msg in messages
    ])

@app.route('/chat/<username>/typing', methods=['POST'])
def set_typing(username):
    if 'username' not in session:
        return jsonify({'success': False}), 401
    key = (session['username'], username)
    typing_status[key] = time.time()
    return jsonify({'success': True})

@app.route('/chat/<username>/is_typing')
def is_typing(username):
    if 'username' not in session:
        return jsonify({'typing': False}), 401
    # Check if the other user is typing to you
    key = (username, session['username'])
    last = typing_status.get(key)
    # Typing if updated in last 3 seconds
    if last and time.time() - last < 3:
        return jsonify({'typing': True})
    return jsonify({'typing': False})

@app.before_request
def update_last_seen():
    if 'username' in session:
        user = User.query.filter_by(username=session['username']).first()
        if user:
            user.last_seen = datetime.utcnow()
            db.session.commit()

@app.route('/follow/<username>', methods=['POST'])
def follow_user(username):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Check if already following
    existing_follow = Follow.query.filter_by(
        follower=session['username'], 
        followed=username
    ).first()
    
    if not existing_follow:
        follow = Follow(session['username'], username)
        db.session.add(follow)
        db.session.commit()
        # --- Notification for follow ---
        if session['username'] != username:
            notification_id = get_next_notification_id()
            message = f"{session['username']} started following you."
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            notification = Notification(notification_id, username, 'follow', message, 0, timestamp)
            db.session.add(notification)
            db.session.commit()
        flash(f'You are now following {username}!', 'success')
    else:
        flash(f'You are already following {username}.', 'info')
    
    return redirect(url_for('view_profile', username=username))

@app.route('/unfollow/<username>', methods=['POST'])
def unfollow_user(username):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Find and remove the follow relationship
    follow = Follow.query.filter_by(
        follower=session['username'], 
        followed=username
    ).first()
    
    if follow:
        db.session.delete(follow)
        db.session.commit()
        flash(f'You have unfollowed {username}.', 'success')
    else:
        flash(f'You were not following {username}.', 'info')
    
    return redirect(url_for('view_profile', username=username))

@app.route('/explore')
def explore():
    print("Registering /explore route")
    posts = TripPost.query.order_by(TripPost.timestamp.desc()).limit(30).all()
    for post in posts:
        post.like_count = TripPostLike.query.filter_by(post_id=post.post_id).count()
        post.liked_by_user = False
        if 'username' in session:
            post.liked_by_user = TripPostLike.query.filter_by(post_id=post.post_id, username=session['username']).first() is not None
        post.comments = TripPostComment.query.filter_by(post_id=post.post_id).order_by(TripPostComment.timestamp.asc()).all()
    return render_template('explore.html', posts=posts)

@app.route('/hashtag/<tag>')
def hashtag(tag):
    posts = TripPost.query.filter(TripPost.caption.ilike(f'%#{tag}%')).order_by(TripPost.timestamp.desc()).all()
    # ...add like/comment info as before...
    return render_template('hashtag.html', tag=tag, posts=posts)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- Socket.IO user session mapping for direct signaling ---
user_sid_map = {}

@socketio.on('connect')
def handle_connect():
    if 'username' in session:
        user_sid_map[session['username']] = request.sid
        print(f"[SocketIO] {session['username']} connected with sid {request.sid}")

@socketio.on('register-username')
def handle_register_username(data):
    username = data.get('username')
    if username:
        user_sid_map[username] = request.sid
        print(f"[SocketIO] Registered username {username} with sid {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    for user, sid in list(user_sid_map.items()):
        if sid == request.sid:
            print(f"[SocketIO] {user} disconnected")
            del user_sid_map[user]

@socketio.on('send_message')
def handle_send_message(data):
    # data: {sender, receiver, content, audio, sticker, ...}
    room = get_room_name(data['sender'], data['receiver'])
    emit('receive_message', data, room=room)

# Helper to get a unique room name for two users

def get_room_name(user1, user2):
    return '__'.join(sorted([user1, user2]))

# --- WebRTC signaling events for 1-to-1 calls ---
@socketio.on('call-user')
def handle_call_user(data):
    print(f"[SocketIO] call-user event data: {data}")
    print(f"[SocketIO] user_sid_map: {user_sid_map}")
    callee = data['to']
    if callee in user_sid_map:
        emit('call-made', data, to=user_sid_map[callee])
    else:
        print(f"[SocketIO] callee {callee} not in user_sid_map")

@socketio.on('call-accepted')
def handle_call_accepted(data):
    print(f"[SocketIO] call-accepted event data: {data}")
    print(f"[SocketIO] user_sid_map: {user_sid_map}")
    caller = data['to']
    if caller in user_sid_map:
        emit('call-accepted', data, to=user_sid_map[caller])
    else:
        print(f"[SocketIO] caller {caller} not in user_sid_map")

@socketio.on('call-rejected')
def handle_call_rejected(data):
    print(f"[SocketIO] call-rejected event data: {data}")
    print(f"[SocketIO] user_sid_map: {user_sid_map}")
    caller = data['to']
    if caller in user_sid_map:
        emit('call-rejected', data, to=user_sid_map[caller])
    else:
        print(f"[SocketIO] caller {caller} not in user_sid_map")

@socketio.on('offer')
def handle_offer(data):
    print(f"[SocketIO] offer event data: {data}")
    print(f"[SocketIO] user_sid_map: {user_sid_map}")
    callee = data['to']
    if callee in user_sid_map:
        emit('offer', data, to=user_sid_map[callee])
    else:
        print(f"[SocketIO] callee {callee} not in user_sid_map")

@socketio.on('answer')
def handle_answer(data):
    print(f"[SocketIO] answer event data: {data}")
    print(f"[SocketIO] user_sid_map: {user_sid_map}")
    caller = data['to']
    if caller in user_sid_map:
        emit('answer', data, to=user_sid_map[caller])
    else:
        print(f"[SocketIO] caller {caller} not in user_sid_map")

@socketio.on('ice-candidate')
def handle_ice_candidate(data):
    print(f"[SocketIO] ice-candidate event data: {data}")
    print(f"[SocketIO] user_sid_map: {user_sid_map}")
    peer = data['to']
    if peer in user_sid_map:
        emit('ice-candidate', data, to=user_sid_map[peer])
    else:
        print(f"[SocketIO] peer {peer} not in user_sid_map")

@socketio.on('end-call')
def handle_end_call(data):
    print(f"[SocketIO] end-call event data: {data}")
    print(f"[SocketIO] user_sid_map: {user_sid_map}")
    peer = data['to']
    if peer in user_sid_map:
        emit('end-call', data, to=user_sid_map[peer])
    else:
        print(f"[SocketIO] peer {peer} not in user_sid_map")

@app.context_processor
def inject_profile_pic_version():
    version = None
    if 'username' in session:
        user = User.query.filter_by(username=session['username']).first()
        if user and user.profile_pic_updated_at:
            version = int(user.profile_pic_updated_at.timestamp())
    if not version:
        from datetime import datetime
        version = int(datetime.utcnow().timestamp())
    return {'profile_pic_version': version}

@app.route('/invitation/<int:invitation_id>')
def invitation_details(invitation_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    invitation = Invitation.query.filter_by(invitation_id=invitation_id).first()
    if not invitation or invitation.invitee != session.get('username'):
        flash('Invitation not found or unauthorized.', 'danger')
        return redirect(url_for('notifications'))
    trip = Trip.query.filter_by(trip_id=invitation.trip_id).first()
    inviter = User.query.filter_by(username=invitation.inviter).first()
    return render_template('invitation_details.html', invitation=invitation, trip=trip, inviter=inviter)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True)