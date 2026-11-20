"""DailyWork Flask application factory.

Migration build: never point this at a production database before completing
all 16 controller parity checks and data reconciliation.
"""
from __future__ import annotations
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def create_app(test_config=None):
    from flask import Flask, jsonify, g, request, session, abort
    import secrets
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.update(
        SECRET_KEY=os.environ.get('FLASK_SECRET_KEY', ''),
        DATABASE_URL=os.environ.get('DATABASE_URL', ''),
        JWT_SECRET=os.environ.get('DAILYWORK_JWT_KEY', ''),
        JWT_ISSUER=os.environ.get('DAILYWORK_JWT_ISSUER', 'DailyWork'),
        JWT_AUDIENCE=os.environ.get('DAILYWORK_JWT_AUDIENCE', 'DailyWorkUsers'),
        ENVIRONMENT=os.environ.get('DAILYWORK_ENVIRONMENT', 'production'),
        TESTING=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('DAILYWORK_ENVIRONMENT','production')!='development',
    )
    if test_config:
        app.config.update(test_config)
    url = app.config['DATABASE_URL']
    if not url:
        raise RuntimeError('DATABASE_URL is required. Use a fresh MySQL database for the migration.')
    if not app.config['TESTING']:
        if not url.startswith('mysql+pymysql://'):
            raise RuntimeError('Production and development migration require MySQL (mysql+pymysql://).')
        if len(app.config['SECRET_KEY']) < 32 or len(app.config['JWT_SECRET']) < 32:
            raise RuntimeError('FLASK_SECRET_KEY and DAILYWORK_JWT_KEY must each be at least 32 characters.')
    engine = create_engine(url, pool_pre_ping=True, pool_recycle=1800)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app.extensions['dailywork_engine'] = engine
    app.extensions['dailywork_sessionmaker'] = Session

    @app.before_request
    def open_session():
        g.db = Session()

    @app.before_request
    def check_csrf():
        if request.method in ('POST','PUT','PATCH','DELETE') and session.get('uid') and not request.headers.get('Authorization','').startswith('Bearer '):
            supplied=request.headers.get('X-CSRF-Token') or request.form.get('csrf_token','')
            if not secrets.compare_digest(str(supplied),str(session.get('csrf',''))):
                abort(403)

    @app.teardown_request
    def close_session(error=None):
        db = g.pop('db', None)
        if db is not None:
            db.rollback()  # a handler must commit explicitly; no accidental writes
            db.close()

    @app.errorhandler(404)
    def not_found(exc):
        return jsonify(message='Not found.'), 404

    from .routes import auth, jobs, applications, payments, webui
    app.register_blueprint(auth.bp)
    app.register_blueprint(jobs.bp)
    app.register_blueprint(applications.bp)
    app.register_blueprint(payments.bp)
    app.register_blueprint(webui.bp)
    @app.get('/health')
    def health():
        from sqlalchemy import text
        g.db.execute(text('SELECT 1'))
        return jsonify(status='ok', framework='flask', database='mysql' if not app.config['TESTING'] else 'test')
    return app
