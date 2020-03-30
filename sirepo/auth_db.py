# -*- coding: utf-8 -*-
u"""Auth database

:copyright: Copyright (c) 2018-2019 RadiaSoft LLC.  All Rights Reserved.
:license: http://www.apache.org/licenses/LICENSE-2.0.html
"""
from __future__ import absolute_import, division, print_function

from pykern.pkdebug import pkdc, pkdexc, pkdlog, pkdp
import threading
import sqlalchemy
import sqlalchemy.orm
import sqlalchemy.ext.declarative


#: sqlite file located in sirepo_db_dir
_SQLITE3_BASENAME = 'auth.db'

#: SQLAlchemy database engine
_engine = None

#: SQLAlchemy session instance
_session = None

#: base for UserRegistration and *User models
UserDbBase = None

#: base for user models
UserRegistration = None

#: roles for each user
UserRole = None

#: Locking of db calls
thread_lock = threading.RLock()


def init(app):
    global _session, _engine, UserDbBase, UserRegistration, UserRole
    assert not _session

    f = _db_filename(app)
    _migrate_db_file(f)
    _engine = sqlalchemy.create_engine(
        'sqlite:///{}'.format(f),
        # We do our own thread locking so no need to have pysqlite warn us when
        # we access a single connection across threads
        connect_args={'check_same_thread': False},
    )
    _session = sqlalchemy.orm.Session(bind=_engine)

    @sqlalchemy.ext.declarative.as_declarative()
    class UserDbBase(object):

        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def delete(self):
            with thread_lock:
                _session.delete(self)
                _session.commit()

        @classmethod
        def delete_all(cls):
            with thread_lock:
                _session.query(cls).delete()
                _session.commit()

        def save(self):
            with thread_lock:
                _session.add(self)
                _session.commit()

        @classmethod
        def search_all_by(cls, **kwargs):
            with thread_lock:
                return _session.query(cls).filter_by(**kwargs).all()

        @classmethod
        def search_by(cls, **kwargs):
            with thread_lock:
                return _session.query(cls).filter_by(**kwargs).first()

        @classmethod
        def search_all_for_column(cls, column, **filter_by):
            with thread_lock:
                return [
                    getattr(r, column) for r
                    in _session.query(cls).filter_by(**filter_by)
                ]

        @classmethod
        def delete_all_for_column_by_values(cls, column, values):
            with thread_lock:
                _session.query(cls).filter(
                    getattr(cls, column).in_(values),
                ).delete(synchronize_session='fetch')
                _session.commit()

        @classmethod
        def delete_all_by_filter(cls, filter_fn_name, *args):
            with thread_lock:
                _session.query(cls).filter(
                    getattr(cls, filter_fn_name)(*args)
                ).delete()
                _session.commit()

    class UserRegistration(UserDbBase):
        __tablename__ = 'user_registration_t'
        uid = sqlalchemy.Column(sqlalchemy.String(8), primary_key=True)
        created = sqlalchemy.Column(sqlalchemy.DateTime(), nullable=False)
        display_name = sqlalchemy.Column(sqlalchemy.String(100))

    class UserRole(UserDbBase):
        __tablename__ = 'user_role_t'
        uid = sqlalchemy.Column(sqlalchemy.String(8), primary_key=True)
        role = sqlalchemy.Column(sqlalchemy.String(100), primary_key=True)

        @classmethod
        def add_roles(cls, uid, roles):
            with thread_lock:
                for r in roles:
                    UserRole(uid=uid, role=r).save()

        @classmethod
        def delete_roles(cls, uid, roles):
            with thread_lock:
                _session.query(cls).filter(
                    cls.uid == uid,
                ).filter(
                    cls.role.in_(roles),
                ).delete(synchronize_session='fetch')
                _session.commit()

    # only creates tables that don't already exist
    UserDbBase.metadata.create_all(_engine)


def init_model(callback):
    with thread_lock:
        callback(UserDbBase)
        UserDbBase.metadata.create_all(_engine)


def _db_filename(app):
    return app.sirepo_db_dir.join(_SQLITE3_BASENAME)


def _migrate_db_file(fn):
    o = fn.new(basename='user.db')
    if not o.exists():
        return
    assert not fn.exists(), \
        'db file collision: old={} and new={} both exist'.format(o, fn)
    try:
        import sqlite3

        c = sqlite3.connect(str(o))
        c.row_factory = sqlite3.Row
        rows = c.execute('SELECT * FROM user_t')
        c2 = sqlite3.connect(str(fn))
        # sqlite3 saves the literal string as the schema
        # so we are formatting it just like SQLAlchemy would
        # format it.
        c2.execute(
            '''CREATE TABLE auth_github_user_t (
        oauth_id VARCHAR(100) NOT NULL,
        user_name VARCHAR(100) NOT NULL,
        uid VARCHAR(8),
        PRIMARY KEY (oauth_id),
        UNIQUE (user_name),
        UNIQUE (uid)
);'''
        )
        for r in rows:
            c2.execute(
                '''
                INSERT INTO auth_github_user_t
                (oauth_id, user_name, uid)
                VALUES (?, ?, ?)
                ''',
                (r['oauth_id'], r['user_name'], r['uid']),
            )
        c.close()
        c2.commit()
        c2.close()
    except sqlite3.OperationalError as e:
        if 'not such table' in e.message:
            return
        raise
    o.rename(o + '-migrated')
    pkdlog('migrated user.db to auth.db')
