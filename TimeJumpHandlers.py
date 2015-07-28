
import cgi
import datetime
import json
import logging
import os
import random
import re
import StringIO
import time

from utils import render_template_text, highest_index_value, highest_picture_index, highest_index_by_date
from Parents import RequestHandlerParent
from DataModels import (Picture, PictureIndex, Greeting, UserFavorite,
                        PictureComment, UniqueTagName, Tag, str_to_dt)

DAYS_IN_YEAR = 365.25
SECS_IN_YEAR = DAYS_IN_YEAR * 3600 * 24

class TimeJumpHandler(RequestHandlerParent):

    def get_index_from_date(self, date_str):
        """Take an input date string of the form 'YYYY:MM:DD hh:mm:ss' and
        return the dateOrderIndex of the closest PictureIndex before it."""

        dateparts = re.split('\W+', date_str)
        if len(dateparts) < 4:
            date = ":".join(dateparts)
        else:
            date = "%s %s" % (":".join(dateparts[0:3]), ":".join(dateparts[3::]))


        pi = PictureIndex.all(
                        ).filter("dateOrderString >", date
                        ).order("dateOrderString").get()
        if pi is None:
            pi = PictureIndex.all(
                            ).filter("dateOrderString <=", date
                            ).order("-dateOrderString").get()
        if pi is None:
            return None
        else:
            logging.info("get_index_from_date results %s" % pi)
            return pi

    def get_shifted_datetime(self, start_date, shift_years):
        shift_years = float(shift_years)

        logging.info('raw date in get_shifted_date: %s' % start_date)

        timedelta = datetime.timedelta(days=DAYS_IN_YEAR*shift_years)
        shifted_datetime = str_to_dt(start_date) + timedelta
        return shifted_datetime

    def get_shifted_date(self, start_date, shift_years):
        """Take an input date string of the form 'YYYY:MM:DD hh:mm:ss', shift
        it by shift_years, and return the new data in the form
        'YYYY:MM:DD hh:mm:ss'.

        Args:
            start_date  -- A string date in the form YYYY:MM:DD hh:mm:ss
            shift_years -- The number of years to shift. Can be specified as
                           string, float, or int, but must be able to survive a
                           float() conversion.
        """
        shifted_datetime = self.get_shifted_datetime(start_date, shift_years)
        shifted_time = shifted_datetime.strftime("%Y:%m:%d %H:%M:%S")
        logging.info('final date in get_shifted_date: %s' % shifted_time)

        return shifted_time

    def get_shifted_index(self, index, shift_years):
        """Generate a new PictureIndex.dateOrderIndex which is the picture in
        the date sequence before the date corresponding to:
            (date of 'index')+shift_years
        If that is not a valid picture (before the first date) take the first
        picture AFTER that date.
        """

        if index is None:
            index = self.get_index_from_request(check_bounds=True)

        current_pi = PictureIndex.get(index=index)
        if current_pi is None:
            return highest_picture_index()

        current_date = current_pi.pix_ref.getDateRaw()
        shifted_date = self.get_shifted_date(current_date, shift_years)
        picture_index = self.get_index_from_date(shifted_date)
        if picture_index:
            return picture_index.dateOrderIndex
        else:
            return highest_picture_index()

    def jump_to_filmstrip(self, index=None, shift_years=None):
        """Redirect to the URL which displays, as its middle picture, the
        filmstrip containing the picture which is shift_years after index.
        The filstrip is 20 pictures long, and goes backwards, so a postive
        10 shift is needed to center the wanted date in the middle."""
        if shift_years:
            shifted_index = self.get_shifted_index(index, shift_years)
        else:
            shifted_index = index
        start_index = shifted_index + 10
        if start_index < 0:
            start_index = 0
        if start_index > highest_picture_index():
            start_index = highest_picture_index()
        self.redirect('/filmstrip/%d' % start_index)

    def jump_to_filmstrip_date(self, date=None, shift_years=None):
        """Redirect to the URL which displays, as its middle picture, the
        filmstrip containing the picture which is shift_years after date.
        The filstrip is 20 pictures long, and goes backwards, so a postive
        10 shift is needed to center the wanted date in the middle."""
        shifted_date = self.get_shifted_date(date, shift_years)
        shifted_index = self.get_index_from_date(shifted_date).dateOrderIndex
        self.jump_to_filmstrip(shifted_index, shift_years=None)

    def jump_to(self, index=None, shift_years=None):
        """Redirect to the URL which displays the picture which is shift_years
        after index."""
        shifted_index = self.get_shifted_index(index, shift_years)
        self.redirect('/nav/%d' % shifted_index)

    def jump_to_date(self, date=None, shift_years=None):
        shifted_date = self.get_shifted_date(date, shift_years)
        shifted_index = self.get_index_from_date(shifted_date).dateOrderIndex
        self.jump_to(shifted_index, shift_years=None)

    def get(self, index=None, years=None):
        """Redirect to the picture closest to 'years' from the current ('index')
        picture"""
        try:
            index = int(float(index))
        except:
            try:
                index = int(float(self.request.get('current_index')))
            except:
                index = 666
                logging.debug(
                    "Something wrong in index read in TimeJumpHandler.get")

        try:
            years = float(years)
        except:
            try:
                years = float(self.request.get('years'))
            except:
                years = -1

        logging.debug("years in TimeJump.get %s" % years)
        self.jump_to(index, years)

    def post(self):
        #TODO
        self.redirect('/highestindex')

class NavigateByDateHandler(TimeJumpHandler):
    def get(self, date_str=None):
        picture_index = self.get_index_from_date(date_str)
        self.redirect('/navperm/%d' % picture_index.count)

class MiriTimeJumpHandler(TimeJumpHandler):
    """Handles time jump requests of the form /miri_is/<years>, and serves
    the picture at which Miri is <years> old.
    """
    birth_date= '2007:10:26 05:30:00'
    def post(self):
        """No post for now"""
        self.error(404)

    def get(self, years='1'):
        """Redirect to the picture at which Miri is 'years' old."""
        years = float(years)
        shifted_date = self.get_shifted_date(self.birth_date, years)
        shifted_index = self.get_index_from_date(shifted_date).dateOrderIndex
        self.redirect('/nav/%d' % shifted_index)

    @classmethod
    def seconds_since_birth(cls):
        """Return the number of seconds between now and cls.birth_date"""
        birth_date = str_to_dt(cls.birth_date)
        timedelta = datetime.datetime.now() - birth_date
        return float(timedelta.total_seconds())

    @classmethod
    def years_since_birth(cls):
        """Return the float number of years since birth."""
        yearsdelta = cls.seconds_since_birth() / SECS_IN_YEAR
        return yearsdelta

    @classmethod
    def random_datetime_since_birth(cls):
        """Return random datetime between now and birth."""
        rand_secs = random.uniform(0, cls.seconds_since_birth())
        delta = datetime.timedelta(seconds=rand_secs)

        rand_dt = str_to_dt(cls.birth_date) + delta
        return rand_dt

class JuliaTimeJumpHandler(MiriTimeJumpHandler):
    """Handles time jump requests of the form /julia_is/<years>, and serves the
    picture at which Julia is <years> old.

    Inherits get and post from MiriTimeJumpHandler
    """
    birth_date= '2010:04:21 07:30:00'

class LinusTimeJumpHandler(MiriTimeJumpHandler):
    """Handles time jump requests of the form /julia_is/<years>, and serves the
    picture at which Linusis <years> old.

    Inherits get and post from MiriTimeJumpHandler
    """
    birth_date= '2015:04:17 07:30:00'

class SameAgeJumpHandler(TimeJumpHandler):
    def get(self, years_old=None):
        """
        Generate a side-by-side picture of the kids at the same age. A
        blank 'years_old' arg will generate a random age and display that.
        """
        if years_old is None:
            julia_age = JuliaTimeJumpHandler.years_since_birth()
            years_old = random.uniform(0, JuliaTimeJumpHandler.years_since_birth())
        else:
            years_old = float(years_old)

        pis = []
        for kid in [MiriTimeJumpHandler, JuliaTimeJumpHandler, LinusTimeJumpHandler]:
            dt = self.get_shifted_datetime(kid.birth_date, years_old)
            pi = self.get_index_from_date(dt.strftime("%Y:%m:%d %H:%M:%S"))
            logging.info(
                'birthday %s, shifted date %s, shift in years %s, index %s' %
                (kid.birth_date, dt, years_old, pi.dateOrderIndex)
            )
            pis.append(pi)

        self.redirect('/side_by_side/%s/%s/%s' % (pis[0].count,
                                                  pis[1].count,
                                                  pis[2].count))

