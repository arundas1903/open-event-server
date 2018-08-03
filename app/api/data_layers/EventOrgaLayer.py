from sqlalchemy.sql import func

from app.api.helpers.db import safe_query
from app.models import db
from app.models.event import Event
from app.models.order import Order
from app.models.ticket import Ticket
from app.models.ticket_holder import TicketHolder
from flask_rest_jsonapi.data_layers.base import BaseDataLayer


class EventOrgaLayer(BaseDataLayer):

    def create_object(self, data, view_kwargs):
        # return super().create_object(data, view_kwargs)
        identifier = 'identifier'

        if view_kwargs.get('identifier').isdigit():
            identifier = 'id'

        event = safe_query(db, Event, identifier, view_kwargs['identifier'], 'event_'+identifier)
        if not event:
            raise ObjectNotFound({'parameter': 'event_identifier'},
                                 "Event with identifier: {} not found".format(view_kwargs['event_identifier']))
        data['id'] = event.id
        data['name'] = event.name
        data['starts_at'] = event.starts_at
        data['payment_currency'] = event.payment_currency

        # Calculate total available tickets for all types of tickets
        tickets_available = db.session.query(func.sum(Ticket.quantity)).filter_by(event_id=event.id).scalar()
        
        data['tickets_available'] = tickets_available if tickets_available else 0

        # Calculate total number of tickets sold for the event
        tickets_sold = db.session.query(Order.event_id).filter_by(event_id=event.id, status='completed').join(TicketHolder).count()
        data['tickets_sold'] = tickets_sold

        # Returns total revenues of all completed orders for the given event
        revenue = db.session.query(func.sum(Order.amount)).filter_by(event_id=event.id, status='completed').scalar()
        
        data['revenue'] = revenue if revenue else 0

        # data['status'] = success
        # data['message'] = response

        return data
