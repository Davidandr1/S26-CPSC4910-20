from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from sqlalchemy import text
from app.db import engine
from app.services.importProducts import ProductAPIService
from app.services.inventoryService import InventoryService
import os
from datetime import datetime, timedelta

class ScheduledPointEventService:
    
    @staticmethod
    def create_scheduled_events(sponsor_id: int, driver_id: int, created_by: int, points: int, reason: str, 
                                scheduled_time: datetime, event_id: int = None, event_name: str = None) -> int:
        with engine.begin() as conn:
            driver = conn.execute(text("SELECT User_ID FROM DRIVERS WHERE User_ID = :did AND Sponsor_ID = :sid"), {"did": driver_id, "sid": sponsor_id}).fetchone()
            if not driver:
                raise ValueError("Driver not found for this sponsor")
            
            result = conn.execute(text("""INSERT INTO SCHEDULED_POINT_EVENTS (Sponsor_ID, Driver_ID, Created_By, Points_Change, Reason, Scheduled_Time, Event_ID, Event_Name) VALUES (:sid, :did, :cb, :p, :r, :st, :eid, :en)"""), {
                "sid": sponsor_id,
                "did": driver_id,
                "cb": created_by,
                "p": points,
                "r": reason,
                "st": scheduled_time,
                "eid": event_id,
                "en": event_name
            })
            return result.lastrowid
        
    @staticmethod
    def create_scheduled_events_bulk(sponsor_id: int, driver_id: list, created_by: int, points: int, reason: str, 
                                scheduled_time: datetime, event_id: int = None, event_name: str = None) -> int:
        created = 0
        for driver_ids in driver_id:
            ScheduledPointEventService.create_scheduled_events(sponsor_id, driver_ids, created_by, points, reason, scheduled_time, event_id, event_name)
            created += 1
        return created
    
    @staticmethod
    def get_scheduled_events_for_sponsor(sponsor_id: int):
        with engine.connect() as conn:
            events = conn.execute(text("""SELECT s.*, u.User_FName, u.User_LName FROM SCHEDULED_POINT_EVENTS s JOIN USERS u ON s.Driver_ID = u.User_ID WHERE s.Sponsor_ID = :sid"""), 
                                  {"sid": sponsor_id}).fetchall()
        return events



    @staticmethod
    def cancel_scheduled_event(event_id: int, sponsor_id: int) -> bool:
        with engine.begin() as conn:
            event = conn.execute(text("""SELECT Scheduled_Status FROM SCHEDULED_POINT_EVENTS WHERE Scheduled_Event_ID = :seid AND Sponsor_ID = :sid"""), 
                                  {"seid": event_id, "sid": sponsor_id}).fetchone()
            if not event:
                raise ValueError("Event not found for this sponsor")
            if event.Scheduled_Status != 'Scheduled':
                raise ValueError("Only scheduled events can be cancelled")
            
            updated_event = conn.execute(text("""UPDATE SCHEDULED_POINT_EVENTS SET Scheduled_Status = 'Cancelled', Processed_Time = :pt WHERE Scheduled_Event_ID = :seid"""), 
                         {"pt": datetime.now(), "seid": event_id})
            return updated_event.rowcount > 0

    @staticmethod
    def process_scheduled_events():
        processed = 0
        with engine.connect() as conn:
            now = datetime.now()
            events = conn.execute(text("""
                SELECT Scheduled_Event_ID, Driver_ID, Event_ID, Sponsor_ID, Created_By, Points_Change, Event_Name, Scheduled_Time, Processed_Time, Reason
                FROM SCHEDULED_POINT_EVENTS 
                WHERE Scheduled_Time <= :now AND Scheduled_Status = 'Scheduled'
                ORDER BY Scheduled_Time ASC
            """), {"now": now}).fetchall()

            for event in events:
                current = conn.execute(text("""SELECT Scheduled_Status, Driver_ID, Sponsor_ID, Points_Change, Reason, Created_By
                                        FROM SCHEDULED_POINT_EVENTS WHERE Scheduled_Event_ID = :seid"""), {"seid": event.Scheduled_Event_ID}).fetchone()
                if not current or current.Scheduled_Status != 'Scheduled':
                    continue

                driver = conn.execute(text("""SELECT User_ID, User_Points FROM DRIVERS WHERE User_ID = :uid AND Sponsor_ID = :sid AND Is_Active = TRUE"""), {"uid": event.User_ID, "sid": event.Sponsor_ID}).fetchone()
                if not driver:
                    conn.execute(text("""UPDATE SCHEDULED_POINT_EVENTS SET Scheduled_Status = 'Failed', Processed_Time = :pt, Reason = 'Driver not found or inactive' WHERE Scheduled_Event_ID = :seid"""), {"pt": datetime.now(), "seid": event.Scheduled_Event_ID})
                    continue

                if event.Points_Change < 0 and driver.User_Points + event.Points_Change < 0:
                    conn.execute(text("""UPDATE SCHEDULED_POINT_EVENTS SET Scheduled_Status = 'Failed', Processed_Time = :pt, Reason = 'Insufficient points' WHERE Scheduled_Event_ID = :seid"""), {"pt": datetime.now(), "seid": event.Scheduled_Event_ID})
                    continue

                conn.execute(text("""UPDATE DRIVERS SET User_Points = User_Points + :change WHERE User_ID = :uid"""), {"change": event.Points_Change, "uid": event.User_ID})
                conn.execute(text("""UPDATE SCHEDULED_POINT_EVENTS SET Scheduled_Status = 'Processed', Processed_Time = :pt WHERE Scheduled_Event_ID = :seid"""), {"pt": datetime.now(), "seid": event.Scheduled_Event_ID})

                conn.execute(text(""" INSERT INTO POINT_TRANSACTIONS (Driver_ID, Actor_User_ID, Points_Changed, Reason, Transaction_Time) VALUES
                                (:did, :actor_id, :points, :reason, :time)"""), 
                                {"did": event.Driver_ID, "actor_id": event.Created_By, "points": event.Points_Change, "reason": f"Scheduled Event: {event.Event_Name}", "time": datetime.now()})
                processed += 1
        return processed

    
                            