import csv
import json
import os
import requests
import uuid

from flask import current_app, render_template
from marrow.mailer import Mailer, Message

from app import make_celery
from app.api.helpers.utilities import strip_tags
from app.models.session import Session
from app.models.speaker import Speaker

"""
Define all API v2 celery tasks here
This is done to resolve circular imports
"""
import logging
import traceback

from app.api.helpers.request_context_task import RequestContextTask
from app.api.helpers.mail import send_export_mail, send_import_mail
from app.api.helpers.notification import send_notif_after_import, send_notif_after_export
from app.api.helpers.db import safe_query
from .import_helpers import update_import_job
from app.models.user import User
from app.models import db
from app.api.exports import event_export_task_base
from app.api.imports import import_event_task_base
from app.models.event import Event
from app.models.order import Order
from app.models.discount_code import DiscountCode
from app.models.ticket_holder import TicketHolder
from app.api.helpers.ICalExporter import ICalExporter
from app.api.helpers.xcal import XCalExporter
from app.api.helpers.pentabarfxml import PentabarfExporter
from app.api.helpers.storage import UploadedFile, upload, UPLOAD_PATHS
from app.api.helpers.db import save_to_db
from app.api.helpers.files import create_save_pdf

celery = make_celery()


@celery.task(name='send.email.post')
def send_email_task(payload, headers):
    data = {"personalizations": [{"to": []}]}
    data["personalizations"][0]["to"].append({"email": payload["to"]})
    data["from"] = {"email": payload["from"]}
    data["subject"] = payload["subject"]
    data["content"] = [{"type": "text/html", "value": payload["html"]}]
    requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        data=json.dumps(data),
        headers=headers,
        verify=False  # doesn't work with verification in celery context
    )


@celery.task(name='send.email.post.smtp')
def send_mail_via_smtp_task(config, payload):
    mailer_config = {
        'transport': {
            'use': 'smtp',
            'host': config['host'],
            'username': config['username'],
            'password': config['password'],
            'tls': config['encryption'],
            'port': config['port']
        }
    }

    mailer = Mailer(mailer_config)
    mailer.start()
    message = Message(author=payload['from'], to=payload['to'])
    message.subject = payload['subject']
    message.plain = strip_tags(payload['html'])
    message.rich = payload['html']
    mailer.send(message)
    mailer.stop()


@celery.task(base=RequestContextTask, name='export.event', bind=True)
def export_event_task(self, email, event_id, settings):
    event = safe_query(db, Event, 'id', event_id, 'event_id')
    user = db.session.query(User).filter_by(email=email).first()
    try:
        logging.info('Exporting started')
        path = event_export_task_base(event_id, settings)
        # task_id = self.request.id.__str__()  # str(async result)
        download_url = path

        result = {
            'download_url': download_url
        }
        logging.info('Exporting done.. sending email')
        send_export_mail(email=email, event_name=event.name, download_url=download_url)
        send_notif_after_export(user=user, event_name=event.name, download_url=download_url, subject_id=event_id)
    except Exception as e:
        print(traceback.format_exc())
        result = {'__error': True, 'result': str(e)}
        logging.info('Error in exporting.. sending email')
        send_export_mail(email=email, event_name=event.name, error_text=str(e))
        send_notif_after_export(user=user, event_name=event.name, error_text=str(e))

    return result


@celery.task(base=RequestContextTask, name='import.event', bind=True)
def import_event_task(self, email, file, source_type, creator_id):
    """Import Event Task"""
    task_id = self.request.id.__str__()  # str(async result)
    user = db.session.query(User).filter_by(email=email).first()
    try:
        logging.info('Importing started')
        result = import_event_task_base(self, file, source_type, creator_id)
        update_import_job(task_id, result['id'], 'SUCCESS')
        logging.info('Importing done..Sending email')
        send_import_mail(email=email, event_name=result['event_name'], event_url=result['url'])
        send_notif_after_import(user=user, event_name=result[
            'event_name'], event_url=result['url'], subject_id=result['id'])
    except Exception as e:
        print(traceback.format_exc())
        result = {'__error': True, 'result': str(e)}
        update_import_job(task_id, str(e), e.status if hasattr(e, 'status') else 'FAILURE')
        send_import_mail(email=email, error_text=str(e))
        send_notif_after_import(user=user, error_text=str(e))

    return result


@celery.task(base=RequestContextTask, name='export.ical', bind=True)
def export_ical_task(self, event_id, temp=True):
    event = safe_query(db, Event, 'id', event_id, 'event_id')

    try:
        if temp:
            filedir = os.path.join(current_app.config.get('BASE_DIR'), 'static/uploads/temp/' + event_id + '/')
        else:
            filedir = os.path.join(current_app.config.get('BASE_DIR'), 'static/uploads/' + event_id + '/')

        if not os.path.isdir(filedir):
            os.makedirs(filedir)
        filename = "ical.ics"
        file_path = os.path.join(filedir, filename)
        with open(file_path, "w") as temp_file:
            temp_file.write(str(ICalExporter.export(event_id), 'utf-8'))
        ical_file = UploadedFile(file_path=file_path, filename=filename)
        if temp:
            ical_url = upload(ical_file, UPLOAD_PATHS['exports-temp']['ical'].format(event_id=event_id))
        else:
            ical_url = upload(ical_file, UPLOAD_PATHS['exports']['ical'].format(event_id=event_id))
        result = {
            'download_url': ical_url
        }
        if not temp:
            event.ical_url = ical_url
            save_to_db(event)

    except Exception as e:
        print(traceback.format_exc())
        result = {'__error': True, 'result': str(e)}

    return result


@celery.task(base=RequestContextTask, name='export.xcal', bind=True)
def export_xcal_task(self, event_id, temp=True):
    event = safe_query(db, Event, 'id', event_id, 'event_id')

    try:
        if temp:
            filedir = os.path.join(current_app.config.get('BASE_DIR'), 'static/uploads/temp/' + event_id + '/')
        else:
            filedir = os.path.join(current_app.config.get('BASE_DIR'), 'static/uploads/' + event_id + '/')

        if not os.path.isdir(filedir):
            os.makedirs(filedir)
        filename = "xcal.xcs"
        file_path = os.path.join(filedir, filename)
        with open(file_path, "w") as temp_file:
            temp_file.write(str(XCalExporter.export(event_id), 'utf-8'))
        xcal_file = UploadedFile(file_path=file_path, filename=filename)
        if temp:
            xcal_url = upload(xcal_file, UPLOAD_PATHS['exports-temp']['xcal'].format(event_id=event_id))
        else:
            xcal_url = upload(xcal_file, UPLOAD_PATHS['exports']['xcal'].format(event_id=event_id))
        result = {
            'download_url': xcal_url
        }
        if not temp:
            event.xcal_url = xcal_url
            save_to_db(event)

    except Exception as e:
        print(traceback.format_exc())
        result = {'__error': True, 'result': str(e)}

    return result


@celery.task(base=RequestContextTask, name='export.pentabarf', bind=True)
def export_pentabarf_task(self, event_id, temp=True):
    event = safe_query(db, Event, 'id', event_id, 'event_id')

    try:
        if temp:
            filedir = os.path.join(current_app.config.get('BASE_DIR'), 'static/uploads/temp/' + event_id + '/')
        else:
            filedir = os.path.join(current_app.config.get('BASE_DIR'), 'static/uploads/' + event_id + '/')

        if not os.path.isdir(filedir):
            os.makedirs(filedir)
        filename = "pentabarf.xml"
        file_path = os.path.join(filedir, filename)
        with open(file_path, "w") as temp_file:
            temp_file.write(str(PentabarfExporter.export(event_id), 'utf-8'))
        pentabarf_file = UploadedFile(file_path=file_path, filename=filename)
        if temp:
            pentabarf_url = upload(pentabarf_file, UPLOAD_PATHS['exports-temp']['pentabarf'].format(event_id=event_id))
        else:
            pentabarf_url = upload(pentabarf_file, UPLOAD_PATHS['exports']['pentabarf'].format(event_id=event_id))
        result = {
            'download_url': pentabarf_url
        }
        if not temp:
            event.pentabarf_url = pentabarf_url
            save_to_db(event)

    except Exception as e:
        print(traceback.format_exc())
        result = {'__error': True, 'result': str(e)}

    return result


@celery.task(base=RequestContextTask, name='export.order.csv', bind=True)
def export_order_csv_task(self, event_id):
    orders = db.session.query(Order).filter_by(event_id=event_id)

    try:
        filedir = os.path.join(current_app.config.get('BASE_DIR'), 'static/uploads/temp/')
        if not os.path.isdir(filedir):
            os.makedirs(filedir)
        filename = "order-{}.csv".format(uuid.uuid1().hex)
        file_path = os.path.join(filedir, filename)

        with open(file_path, "w") as temp_file:
            writer = csv.writer(temp_file)
            from app.api.helpers.csv_jobs_util import export_orders_csv
            content = export_orders_csv(orders)
            for row in content:
                writer.writerow(row)
        order_csv_file = UploadedFile(file_path=file_path, filename=filename)
        order_csv_url = upload(order_csv_file,
                               UPLOAD_PATHS['exports-temp']['csv'].format(event_id=event_id, identifier=''))
        result = {
            'download_url': order_csv_url
        }
    except Exception as e:
        print(traceback.format_exc())
        result = {'__error': True, 'result': str(e)}

    return result


@celery.task(base=RequestContextTask, name='export.order.pdf', bind=True)
def export_order_pdf_task(self, event_id):
    orders = db.session.query(Order).filter_by(event_id=event_id)
    event = db.session.query(Event).filter_by(id=int(event_id)).first()
    discount_code = db.session.query(DiscountCode).filter_by(event_id=event_id)
    try:
        order_pdf_url = create_save_pdf(
            render_template('pdf/orders.html', event=event, event_id=event_id, orders=orders,
                            discount_code=discount_code),
            UPLOAD_PATHS['exports-temp']['pdf'].format(event_id=event_id, identifier=''))
        result = {
            'download_url': order_pdf_url
        }
    except Exception as e:
        print(traceback.format_exc())
        result = {'__error': True, 'result': str(e)}

    return result


@celery.task(base=RequestContextTask, name='export.attendees.csv', bind=True)
def export_attendees_csv_task(self, event_id):
    attendees = db.session.query(TicketHolder).filter_by(event_id=event_id)
    try:
        filedir = os.path.join(current_app.config.get('BASE_DIR'), 'static/uploads/temp/')
        if not os.path.isdir(filedir):
            os.makedirs(filedir)
        filename = "attendees-{}.csv".format(uuid.uuid1().hex)
        file_path = os.path.join(filedir, filename)

        with open(file_path, "w") as temp_file:
            writer = csv.writer(temp_file)
            from app.api.helpers.csv_jobs_util import export_attendees_csv
            content = export_attendees_csv(attendees)
            for row in content:
                writer.writerow(row)
        attendees_csv_file = UploadedFile(file_path=file_path, filename=filename)
        attendees_csv_url = upload(attendees_csv_file,
                                   UPLOAD_PATHS['exports-temp']['csv'].format(event_id=event_id, identifier=''))
        result = {
            'download_url': attendees_csv_url
        }
    except Exception as e:
        print(traceback.format_exc())
        result = {'__error': True, 'result': str(e)}

    return result


@celery.task(base=RequestContextTask, name='export.attendees.pdf', bind=True)
def export_attendees_pdf_task(self, event_id):
    attendees = db.session.query(TicketHolder).filter_by(event_id=event_id)
    try:
        attendees_pdf_url = create_save_pdf(
            render_template('pdf/attendees_pdf.html', holders=attendees),
            UPLOAD_PATHS['exports-temp']['pdf'].format(event_id=event_id, identifier=''))
        result = {
            'download_url': attendees_pdf_url
        }
    except Exception as e:
        print(traceback.format_exc())
        result = {'__error': True, 'result': str(e)}

    return result


@celery.task(base=RequestContextTask, name='export.sessions.csv', bind=True)
def export_sessions_csv_task(self, event_id):
    sessions = db.session.query(Session).filter_by(event_id=event_id)
    try:
        filedir = os.path.join(current_app.config.get('BASE_DIR'), 'static/uploads/temp/')
        if not os.path.isdir(filedir):
            os.makedirs(filedir)
        filename = "sessions-{}.csv".format(uuid.uuid1().hex)
        file_path = os.path.join(filedir, filename)

        with open(file_path, "w") as temp_file:
            writer = csv.writer(temp_file)
            from app.api.helpers.csv_jobs_util import export_sessions_csv
            content = export_sessions_csv(sessions)
            for row in content:
                writer.writerow(row)
        sessions_csv_file = UploadedFile(file_path=file_path, filename=filename)
        sessions_csv_url = upload(sessions_csv_file,
                                  UPLOAD_PATHS['exports-temp']['csv'].format(event_id=event_id, identifier=''))
        result = {
            'download_url': sessions_csv_url
        }
    except Exception as e:
        print(traceback.format_exc())
        result = {'__error': True, 'result': str(e)}

    return result


@celery.task(base=RequestContextTask, name='export.speakers.csv', bind=True)
def export_speakers_csv_task(self, event_id):
    speakers = db.session.query(Speaker).filter_by(event_id=event_id)
    try:
        filedir = os.path.join(current_app.config.get('BASE_DIR'), 'static/uploads/temp/')
        if not os.path.isdir(filedir):
            os.makedirs(filedir)
        filename = "speakers-{}.csv".format(uuid.uuid1().hex)
        file_path = os.path.join(filedir, filename)

        with open(file_path, "w") as temp_file:
            writer = csv.writer(temp_file)
            from app.api.helpers.csv_jobs_util import export_speakers_csv
            content = export_speakers_csv(speakers)
            for row in content:
                writer.writerow(row)
        speakers_csv_file = UploadedFile(file_path=file_path, filename=filename)
        speakers_csv_url = upload(speakers_csv_file,
                                  UPLOAD_PATHS['exports-temp']['csv'].format(event_id=event_id, identifier=''))
        result = {
            'download_url': speakers_csv_url
        }
    except Exception as e:
        print(traceback.format_exc())
        result = {'__error': True, 'result': str(e)}

    return result


@celery.task(base=RequestContextTask, name='export.sessions.pdf', bind=True)
def export_sessions_pdf_task(self, event_id):
    sessions = db.session.query(Session).filter_by(event_id=event_id)
    try:
        sessions_pdf_url = create_save_pdf(
            render_template('pdf/sessions_pdf.html', sessions=sessions),
            UPLOAD_PATHS['exports-temp']['pdf'].format(event_id=event_id, identifier=''))
        result = {
            'download_url': sessions_pdf_url
        }
    except Exception as e:
        print(traceback.format_exc())
        result = {'__error': True, 'result': str(e)}

    return result
