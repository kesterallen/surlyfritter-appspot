from __future__ import with_statement

import cgi
import datetime
import json
import logging
import os
import random
import re
import StringIO
import time
import wsgiref.handlers

from pprint import pformat

import lib.cloudstorage as gcs

from google.appengine.api.images import CORRECT_ORIENTATION
from google.appengine.api import app_identity
from google.appengine.api import images
from google.appengine.api import mail
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.ext.db import GqlQuery
from google.appengine.ext import blobstore
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.mail_handlers import InboundMailHandler
from google.appengine.runtime.apiproxy_errors import OverQuotaError
from google.appengine.runtime import DeadlineExceededError

from Parents import RequestHandlerParent

from TimeJumpHandlers import (TimeJumpHandler, NavigateByDateHandler,
                              MiriTimeJumpHandler, JuliaTimeJumpHandler,
                              LinusTimeJumpHandler, SameAgeJumpHandler,
                              DAYS_IN_YEAR, SECS_IN_YEAR)

from ImageHandlers import (ReplaceImageHandler, ImageServingUrl,
                           ImageParent, ImageByDateHandler,
                           ImageByJpgIndexHandler, ImageByNameHandler,
                           ImageByOrderAddedHandler, ImageByIndexHandler,
                           FilmstripHandler, ImagesByTagHandler)

from Recipes import RecipesHandler, PancakesHandler

from DataModels import (Picture, PictureIndex, Greeting, UserFavorite,
                        PictureComment, UniqueTagName, Tag, str_to_dt)

from utils import (render_template_text, highest_index_value,
                   highest_picture_index, highest_index_by_date,
                   cn_hpi, cn_hpi_date)

DEFAULT_SLIDE_COUNT = 4

GCS_BUCKET_NAME = os.environ.get('BUCKET_NAME',
                                 app_identity.get_default_gcs_bucket_name())
GCS_BUCKET = '/' + GCS_BUCKET_NAME

AUTHORIZED_UPLOADERS = ["Kester Allen <kester@gmail.com>",
                        "Abigail Paske <apaske@gmail.com>",
                        "Abby Paske <apaske@gmail.com>", ]
NOTIFICATION_SENDER = "Kester Allen <kester@gmail.com>"
NOTIFICATION_RECEIVER = "kester@gmail.com, apaske@gmail.com"
BLOBSTORE_UPLOAD_DEFAULT = True
MAX_IMAGE_UPLOAD_SIZE = 1000000 #  1 MB
MAX_TRANSACTION_SIZE = 10000000 # 10 MB


# Functions:
#
def get_date_for_slides(pi_count, is_compact=True):
    date = DateByIndexHandler().getText(pi_count, is_compact)
    return date

def notification_email_html(subject, body, html=None, to=None):
    sender = NOTIFICATION_SENDER
    if to is None:
        to = sender
    if html is None:
        html = body + "<p>click 'Display images below to see images'<p>"
    full_subject = 'surlyfritter added %s' % subject
    mail.send_mail(
        sender=sender, to=to, subject=full_subject, body=body, html=html)

def notification_email(subject, body, to=None):
    sender = NOTIFICATION_SENDER
    if to is None:
        to = sender
    full_subject = 'surlyfritter added %s' % subject
    mail.send_mail(sender=sender, to=to, subject=full_subject, body=body)

def add_picture(image, name, isBlobstore=BLOBSTORE_UPLOAD_DEFAULT):

    # Check if image is longer than 1MB, return if it is.
    #
    if isBlobstore:
        blobInfo = blobstore.BlobInfo.get(image)
        #image_size = blobInfo.size
        image_size = 666#blobInfo.size #TODO:  fix this
    else:
        image_size = len(image)

    logging.info('Display.add_picture: image size for %s is %s .' %
        (name, image_size))

    if image_size > MAX_IMAGE_UPLOAD_SIZE:
        msg = 'Display.add_picture: image "%s" is too large. Skipping.' % name
        logging.info(msg)
        notification_email("picture FAILURE", msg)
        return

    # Create the picture:
    #
    logging.info(
        "starting Picture add in add_picture for %s with isBlobstore %s" %
        (name, isBlobstore))
    picture = Picture()
    picture.setPictureAndName(image=image, name=name, isBlobstore=isBlobstore)
    picture.put()
    logging.info("done Picture add in add_picture for %s" % name)

    # Index the picture:
    #
    logging.info("starting PictureIndex add in add_picture")
    count = highest_index_value(cn_hpi , 'count') + 1
    dateOrderIndex = highest_index_by_date() + 1
    dateOrderString = get_date_order_string(count=count,
                                            rawDate=picture.getDateRaw())

    # Update the highestPictureIndex memcache value:
    memcacheStatus = memcache.set(cn_hpi, count)
    if not memcacheStatus:
        logging.debug("memcaching for count failed in add_picture")
    memcacheStatus = memcache.set(cn_hpi_date, dateOrderIndex)
    if not memcacheStatus:
        logging.debug("memcaching for dateOrderIndex failed in add_picture")

    pictureIndex = PictureIndex.make_picture_index(picture,
                                                   count,
                                                   dateOrderIndex,
                                                   dateOrderString)
    pictureIndex.put()
    logging.info("done PictureIndex add in add_picture")

    return pictureIndex

def get_date_order_string(count, rawDate=None):

    if rawDate:
        logging.info(
            'Using rawDate argument %s for dateValue in get_date_order_string' %
            rawDate)
        dateValue = rawDate
    else:
        pictureIndex = PictureIndex.get(count, by_date=False)

        isExivDate = pictureIndex.pix_ref.isExivDate()
        if isExivDate:
            dateValue = pictureIndex.pix_ref.getDateRaw()
            logging.info(
                'Using picture.getDateRaw %s for dateValue '
                'in get_date_order_string' % dateValue)
        else:
            dateValue = PictureIndex.defaultDate
            logging.info(
                'Using default date %s for dateValue in get_date_order_string' %
                PictureIndex.defaultDate)

    dateOrderString = "%s %0004d" % (dateValue, count)
    logging.info('Generated dateOrderString %s for count=%s, rawDate=%s' %
                 (dateOrderString, count, rawDate))
    return dateOrderString

def email_upload_summary(picture_indices, subject=''):
    template = """
<li>
  Image %s<br/>
  <a href="http://surlyfritter.appspot.com/perm/%d">
    <img src="http://surlyfritter.appspot.com/imgperm/%d"/>
  </a>
  <br/>
</li>"""
    msg = """
New pictures uploaded:\n
<ul>
"""
    for pi in picture_indices:
        msg = msg + (template % (pi.pix_ref.name, pi.count, pi.count))
    msg += """
</ul>
"""
    outsub = "email upload pictures: %s" % subject
    notification_email_html(subject=outsub, body=msg, to=NOTIFICATION_RECEIVER)

# Operations classes:
#
class SideBySideHandler(RequestHandlerParent):
    def get(self, counts_from_request='/600/601'):
        """
        The index arguments should be PictureIndex.count values, not
        PictureIndex.dateOrderIndex.
        """

        m_date = str_to_dt(MiriTimeJumpHandler.birth_date)
        j_date = str_to_dt(JuliaTimeJumpHandler.birth_date)
        l_date = str_to_dt(LinusTimeJumpHandler.birth_date)

        count_indices = [int(c) for c in counts_from_request.split("/") if c]

        pics = []
        for count_index in count_indices:
            pi = PictureIndex.get(count_index, by_date=False)
            if pi:

                date = pi.datetime
                pics.append({
                    'picture_index': pi,
                    'date': date,
                    'miri_age': float((date - m_date).days) / DAYS_IN_YEAR,
                    'julia_age': float((date - j_date).days) / DAYS_IN_YEAR,
                    'linus_age': float((date - l_date).days) / DAYS_IN_YEAR,
                })
            else:
                logging.info("skipping null picture_index %s" % count_index)


        template_values = { 'pics': pics,
                            'count_index': pics[0]['picture_index'].count,
                          }
        template_text = render_template_text('side_by_side.html',
                                             template_values)
        self.write_output(template_text)

class GetDateOrderString(RequestHandlerParent):
    def get(self):
        index = self.get_index_from_request()
        pictureIndex = PictureIndex.get(index, by_date=False)
        self.write_output("date order string is %s" %
                         pictureIndex.dateOrderString)

class DateOrderIndexByCountHandler(RequestHandlerParent):
    def get(self):
        index = self.get_index_from_request()
        pictureIndex = PictureIndex.get(index, by_date=False)
        self.write_output(pictureIndex.dateOrderIndex)

class CountByDateOrderIndexHandler(RequestHandlerParent):
    def get(self):
        index = self.get_index_from_request()
        pictureIndex = PictureIndex.get(index, by_date=True)
        self.write_output(pictureIndex.count)

class AddDateOrderString(RequestHandlerParent):
    def get(self):
        index = self.get_index_from_request()

        logging.info("index: %s" % index)
        self.write_output("index: %s" % index)
        pictureIndex = PictureIndex.all().filter('count', index).get()
        logging.info("index: %s" % pformat(pictureIndex))
        if pictureIndex is None:
            self.write_output("no picture index!")
            return

        self.write_output(pformat(pictureIndex))
        dateOrderString = get_date_order_string(index)
        pictureIndex.dateOrderString = dateOrderString
        pictureIndex.put()
        self.write_output("added %s" % dateOrderString)

# pictureIndex.count 22 should be dateOrderIndex 0
# pictureIndex.count 0 should be dateOrderIndex 1
class SetDateOrderIndexHandler(RequestHandlerParent):
    def get(self):
        count = self.get_index_from_request('count')
        dateOrderIndex = self.get_index_from_request('dateorderindex')
        logging.info("setting PictureIndex count %s to dateOrderIndex %s" %
                     (count, dateOrderIndex))
        pictureIndex = PictureIndex.get(index=count, by_date=False)
        pictureIndex.dateOrderIndex = dateOrderIndex
        pictureIndex.put()

class FixDateOrderIndexHandler(RequestHandlerParent):
    def get(self):
        do_from = int(self.request.get('from'))
        do_to = int(self.request.get('to'))
        picture_index = PictureIndex.get(index=do_from)
        logging.debug('from is %s to is %s' % (do_from, do_to))
        if picture_index:
            logging.debug('putting')
            picture_index.dateOrderIndex = do_to
            picture_index.put()
            logging.debug('done putting')
        else:
            logging.debug('no pi')

class HighestIndexHandler(RequestHandlerParent):
    def post(self):
        self.redirect('/highestindex')

    def get(self):
        text = ("<html><body>highest count is %d highest date-ordered index "
                "is %d</body></html>" % (
               highest_index_value(cn_hpi , 'count'),
               highest_index_value(cn_hpi_date, 'count')))

        self.write_output(text)

class MakeFavoritesPage(RequestHandlerParent):
    def post(self):
        user = users.get_current_user()
        user_favorites = UserFavorite.all().filter('user =', user).order('-date')

        template_values = {
            'user': user,
            'user_favorites': user_favorites,
        }

        template_text_navbar = render_template_text('navbar.html',
                                                    template_values)
        template_values['navbar'] = template_text_navbar

        template_text = render_template_text('user_page.html', template_values)
        self.write_output(template_text)

class StartSlideShow(RequestHandlerParent):
    def post(self):
        slideshow_frequency = self.request.get('slideshow_frequency')
        self.redirect('/?slideshow_flag=1&slideshow_frequency=' +
                      slideshow_frequency)

class MarkAsFavorite(RequestHandlerParent):
    def post(self):
        # PictureIndex.count is zero-based, and so is current_index
        #
        current_index = int(self.request.get('current_index'))
        picture_index = PictureIndex.get(index=current_index)

        user_favorite = UserFavorite()
        user_favorite.user = users.get_current_user()
        user_favorite.picture_index = picture_index
        user_favorite.put()

        self.redirect("/n")

class ClearFavorites(RequestHandlerParent):
    def post(self):
        user = users.get_current_user()
        user_favorites = UserFavorite.all().filter('user = ', user)
        for user_favorite in user_favorites:
            user_favorite.delete()

        self.redirect("/n")

class AddTag(RequestHandlerParent):
    def post(self):
        # Get the tag(s) text from the user submission, remove illegal
        # characters, split on commas, and lowercase/strip the tags:
        tag_text = self.request.get('tag_name')
        tag_names = re.sub('[^,\w]', ' ', tag_text).split(',')
        tag_names = set([tag_name.strip().lower() for tag_name in tag_names])
        date_order_index = self.get_index_from_request('count')
        count = PictureIndex.dateOrderIndexToCount(date_order_index)

        for tag_name in tag_names:
            uniqueTagName = UniqueTagName.all().filter('name = ', tag_name).get()
            if not uniqueTagName:
                uniqueTagName = UniqueTagName()
                uniqueTagName.name = tag_name
                uniqueTagName.tag_count = 0
                uniqueTagName.put()

            # Check if this tag is a duplicate on this picture:
            oldTags = Tag.all().filter('count = ', count)
            isDuplicateTag = False
            for oldTag in oldTags:
                if oldTag.name_ref.name == tag_name:
                    isDuplicateTag = True

            if not isDuplicateTag:
                tag = Tag()
                tag.name_ref = uniqueTagName
                tag.count = count
                tag.date = PictureIndex.get(count, by_date=False).pix_ref.date
                tag.put()

                if uniqueTagName.tag_count:
                    uniqueTagName.tag_count += 1
                else:
                    uniqueTagName.tag_count = 1
                uniqueTagName.put()

                memcache_name = Tag.memcacheName(count)
                #memcache_name = get_memcache_name(Tag, count)
                memcacheTagNames = memcache.get(memcache_name)
                if not memcacheTagNames:
                    memcacheTagNames = []
                memcacheTagNames.append(str(uniqueTagName.name))
                memcacheStatus = memcache.set(memcache_name, memcacheTagNames)
                if not memcacheStatus:
                    logging.debug("memcaching failed in AddTag")

        memcache.set("template_text_%s_%s" % (count, ''), None)
        msg = ("The tag(s) '%s' was added to <br>"
               "<a href='http://surlyfritter.appspot.com/navperm/%d'>"
               "<img src='http://surlyfritter.appspot.com/imgperm/%d'/>"
               "</a>" % (
               tag_text, count, count))
        notification_email_html("tag", msg)

        #self.redirect('/nav/%d' % date_order_index)
        url = '/flush?redirect=/nav/%s' % date_order_index
        self.redirect(url)

class AddComment(RequestHandlerParent):
    def post(self):
        picture_comment = PictureComment()

        if users.get_current_user():
            picture_comment.author = users.get_current_user()

        dateOrderIndex = self.get_index_from_request('current_index',
                                                     check_bounds=True)
        count = PictureIndex.dateOrderIndexToCount(dateOrderIndex)

        picture_comment.content = self.request.get('content')
        picture_comment.picture_index = count
        picture_comment.put()

        memcache.set("template_text_%s_%s" % (count, ''), None)
        msg = ('Display.py:AddComment:\n\tComment "%s" added to\n\tpermalink '
               'http://surlyfritter.appspot.com/n?i=%d&mode=count' % (
               picture_comment.content, count))
        notification_email("comment", msg)
        self.redirect('/nav/%d' % dateOrderIndex)

class AddGreeting(RequestHandlerParent):
    def post(self):
        greeting = Greeting()

        if users.get_current_user():
            greeting.author = users.get_current_user()

        greeting.content = self.request.get('content')
        greeting.put()

        msg = ('Display.py:AddGreeting:\n\tGreeting "%s" added to\n\tpermalink '
               'http://surlyfritter.appspot.com/n?i=%d&mode=count' % (
               greeting.content, count))
        notification_email("greeting", msg)
        self.redirect('/')

class FeedHandler(RequestHandlerParent):
    def get(self):
        pictureIndexes = db.GqlQuery("select * from PictureIndex "
                                     "order by dateOrderIndex DESC limit 5")
        template_values = { 'picture_indexes': pictureIndexes }
        template_text = render_template_text('feed.xml', template_values)
        self.write_output(template_text)

class ShowUploadPage(RequestHandlerParent):
    def get(self):
        user = users.get_current_user()
        if True: #TODO: removing user requirement to upload in bulk, revert this 2019-07-29 #if user and users.is_current_user_admin():
            blob_upload_url = blobstore.create_upload_url("/blobupload")
            welcome_text = 'Hello '
            if user:
                welcome_text += user.nickname()

            template_values = {
                'blob_upload_url': blob_upload_url,
                'welcome_text': welcome_text,
            }

            template_text = render_template_text('upload_pictures.html',
                                                 template_values)
            self.write_output(template_text)
        else:
            self.redirect('/')

class BlobViewPicture(blobstore_handlers.BlobstoreDownloadHandler):
    def get(self):
        logging.info('BlobViewPicture: get key')
        blob_key = self.request.get('key')
        logging.info('BlobViewPicture: key is %s' % blob_key)

        if blobstore.get(blob_key):
            logging.info('BlobViewPicture: blobstore got key')
            self.send_blob(blob_key)
        else:
            logging.info('blobstore.get() failed')
            self.error(404)
        return

class BlobUploadNewPicture(blobstore_handlers.BlobstoreUploadHandler):
    def post(self):
        logging.info('start get_uploads in BlobUploadNewPicture')

        # The get_uploads method returns a list of BlobInfo objects.
        upload_files = self.get_uploads()
        logging.info('done get_uploads')
        logging.info('upload_files: %s' % upload_files)

        pis = []
        images_size_sum = 0
        for upload_file in upload_files:

            images_size_sum += upload_file.size
            if images_size_sum > MAX_TRANSACTION_SIZE:
                msg = ('BlobUploadNewPicture.post: upload(s) is/are '
                       'too large for the transaction. Skipping %s.' %
                       upload_file)
                logging.info(msg)
                notification_email(
                    "picture FAILURE overall transaction size caught in"
                    "BlobUploadNewPicture",
                    msg)
                continue

            blob_key = upload_file.key()
            filename = upload_file.filename

            pi = add_picture(blob_key, filename, isBlobstore=True)
            pis.append(pi)

        #email_upload_summary(pis, subject='')

        self.redirect('/flush')

class UploadNewPicture(RequestHandlerParent):
    def post(self):
        decoded_image = self.request.POST.get('file_to_upload').file.read()
        name = self.request.POST.get('file_to_upload').filename
        add_picture(decoded_image, name)

        user = users.get_current_user()
        logging.info('Uploading picture by %s from upload page.' % user)

        self.redirect('/showuploadpage?picture_name=' + name)

class NavigatePictures(RequestHandlerParent):
    def post(self):
        self.redirect('/nav/%d' % self.get_current_index())

    def get(self, index=None, num_slides=DEFAULT_SLIDE_COUNT):
        """
        Overload num_slides: if it is 'back', the user has just clicked the
        left carousel arrow on the first picture in the carousel slideset, and
        should be directed to the LAST picture in the next (newer in time)
        slideset.
        """
        if num_slides == 'back':
            num_slides = DEFAULT_SLIDE_COUNT
            is_carousel_back = True
        else:
            num_slides = int(float(num_slides))
            if num_slides < 1:
                num_slides = 1
            if num_slides > 30:
                num_slides = 30
            is_carousel_back = False

        try:
            # Bail out if there are no pics:
            #
            if highest_picture_index() < 0:
                self.write_output("no pictures!")
                return

            #Determine login and admin status:
            #
            admin_flag = False
            user = users.get_current_user()
            if user:
                nickname = user.nickname()
                welcome_text = 'Hello ' +  nickname
                url = users.create_logout_url(self.request.uri)
                url_linktext = 'Logout'
                if users.is_current_user_admin():
                    admin_flag = True
            else:
                nickname = 'notloggedin'
                welcome_text = ''
                url = users.create_login_url(self.request.uri)
                url_linktext = 'Login'

            # Use the order-added index, or the date-ordered index. The default
            # behavior is to use order-added in order to preserve old bookmarks
            # and links.
            #
            if index is not None:
                # Convert floating point number to int, if necessary:
                index = int(float(index))
                logging.info('NavigatePictures.get: index is not None: %s' % index)
            else:
                logging.info('NavigatePictures.get: index is None')

            dateOrderIndex, count, index_mode = self.get_indices(index)

            # Memcache template text to speed things up
            memcache_name = "template_text_%s_%s_%s" % (count, num_slides, nickname)
            #memcache_name = get_memcache_name(NavigatePictures, count=count)
            template_text = memcache.get(memcache_name)
            if template_text is None:
                prev_index = self.get_prev_index(index)
                newest_index = highest_picture_index()

                # TODO-switchdirection: reverse these
                slide_dois = [dateOrderIndex - i for i in range(num_slides)]
                slide_dois = [i if i > 0 else 0 for i in slide_dois]
                pis = PictureIndex.all(
                                 ).filter('dateOrderIndex in', slide_dois
                                 ).order('-dateOrderIndex'
                                 ).fetch(num_slides)

                if len(pis) > 0:
                    thedate = pis[0].datetime
                    count_index = int(pis[-1].count)
                else:
                    thedate = '(no date available)'
                    count_index = 0
                logging.info("count_index is %s, thedate is %s", count_index, thedate)

                pi_dicts = [pi.template_repr() for pi in pis]
                template_values = {
                    'carousel_slides':  pi_dicts,

                    'count_index':      count_index,
                    'prev_index':       prev_index,
                    'current_index':    dateOrderIndex,
                    'next_index':       self.get_next_index(index),
                    'newest_index':     newest_index,
                    'random_index':     random.randint(0, highest_picture_index()),

                    'tags':             TagCloudHandler.get_cloud_tags(),

                    'url_linktext':     url_linktext,
                    'url':              url,
                    'user':             user,
                    'admin_flag':       admin_flag,
                    'welcome_text':     welcome_text,
                    'thedate':          thedate,
                    'blob_upload_url':  blobstore.create_upload_url('/blobupload'),
                    'is_carousel_back': is_carousel_back,
                }
                template_text = render_template_text('navigate.html', template_values)
                memcacheStatus = memcache.set(memcache_name, template_text)
                logging.info("done memcache of template_text")
                if not memcacheStatus:
                    logging.debug("memcaching.set failed for template_text")
            else:
                logging.debug("memcaching.get worked for template_text")

            self.write_output(template_text)
        except OverQuotaError as oqe:
            template_text = render_template_text('over_quota.html', {})
            self.write_output(template_text)
            return

    def get_indices_with_index(self, index):
        """An index was specified, use it to get the date_index,
        count index, and index_mode"""

        # Permalinks are of the form /navperm/\d+ (explict) or /\d+ (implicit):
        #
        req_path = self.request.path
        is_permalink_exp = req_path.startswith('/navperm') or req_path.startswith('/perm')
        is_permalink_imp = re.match(r'/\d+', req_path) is not None
        is_permalink = is_permalink_exp or is_permalink_imp
        if is_permalink:
            index_mode = 'count'
            count = int(float(index))
            date_index = PictureIndex.countToDateOrderIndex(count)
        else:
            index_mode = 'date'
            date_index = int(float(index))
            count = PictureIndex.dateOrderIndexToCount(date_index)

        logging.info('NavigatePictures.get_indices_with_index: %s %s %s' %
                     (date_index, count, index_mode))

        if date_index < 0:
            date_index = 0
        if count < 0:
            count = 0

        hpi = highest_picture_index()
        if date_index > hpi:
            date_index = hpi

        return date_index, count, index_mode

    def get_indices_without_index(self):
        """No index was specified. Return the current date_index, count,
        and mode"""

        index_mode = self.request.get('mode')
        if index_mode == 'date':
            date_index = self.get_current_index(check_bounds=True)
            count = PictureIndex.dateOrderIndexToCount(date_index)
        else:
            # If the user is requesting 'http://surlyfritter.appspot.com', give
            # them the latest date-ordered pic, otherwise assume it is a
            # count-ordered request:
            #
            is_root_requested= (self.request.get('current_index') == "" and
                                self.request.get('i') == "" and
                                self.request.get('mode') == "")
            if is_root_requested:
                index_mode = 'date'
                date_index = self.get_current_index(check_bounds=True)
                count = PictureIndex.dateOrderIndexToCount(date_index)
            else:
                index_mode = 'count'
                # A count index may be higher than the largest date-order
                # index, so don't bounds-check it.
                count = self.get_current_index(check_bounds=False)
                date_index = PictureIndex.countToDateOrderIndex(count)

        logging.info('NavigatePictures.get_indices_without_index: %s %s %s' %
                     (date_index, count, index_mode))

        return date_index, count, index_mode

    def get_indices(self, index):
        """Return triplet of date-ordered index, count-ordered index, and
        index_mode, based on what the input index var is, and if a index_mode
        has been specified."""

        if index is None:
            date_index, added_index, mode = self.get_indices_without_index()
        else:
            date_index, added_index, mode = self.get_indices_with_index(index)

        return date_index, added_index, mode

    def get_current_index(self, check_bounds=True):
        current_index = self.request.get('current_index')
        if current_index == "":
            current_index = self.request.get('i')

        if current_index:
            current_index = int(current_index)

            if check_bounds:
                if current_index > highest_picture_index():
                    current_index = highest_picture_index()
                if current_index < 0:
                    current_index = 0
        else:
            current_index = highest_picture_index()

        return current_index

    def get_next_index(self, index):
        if not index:
            index = self.get_current_index()
        next_index = index + 1
        if next_index > highest_picture_index():
            next_index = highest_picture_index()

        return next_index

    def get_prev_index(self, index):
        if not index:
            index = self.get_current_index()
        prev_index = index - 1
        if prev_index < 0:
            prev_index = 0

        return prev_index

class NavigatePicturesNew(NavigatePictures):
    def post(self):
        self.redirect('/nav/%d' % self.get_current_index())

    def get(self, index=None, ignore=None):

        try:
            # Bail out if there are no pics:
            #
            if highest_picture_index() < 0:
                self.write_output("no pictures!")
                return

            #Determine login and admin status:
            #
            admin_flag = False
            user = users.get_current_user()
            if user:
                nickname = user.nickname()
                welcome_text = 'Hello ' +  nickname
                url = users.create_logout_url(self.request.uri)
                url_linktext = 'Logout'
                if users.is_current_user_admin():
                    admin_flag = True
            else:
                nickname = 'notloggedin'
                welcome_text = ''
                url = users.create_login_url(self.request.uri)
                url_linktext = 'Login'

            # Use the order-added index, or the date-ordered index. The default
            # behavior is to use order-added in order to preserve old bookmarks
            # and links.
            #
            if index is not None:
                # Convert floating point number to int, if necessary:
                index = int(float(index))

            dateOrderIndex, count, index_mode = self.get_indices(index)

            prev_index = self.get_prev_index(index)
            newest_index = highest_picture_index()

            # TODO: Use something better than this:
            # TODO: This is getting bad dateOrderIndexs for some
            slide = None
            slide_index = dateOrderIndex
            while slide is None:
                pis = PictureIndex.all(
                          ).filter('dateOrderIndex ==', slide_index
                          ).fetch(1)
                try:
                    slide = pis[0]
                except IndexError as err:
                    old_slide_index = slide_index
                    slide_index -= 1
                    logging.debug(
                        "dateOrderIndex %s failed, retrying with new index %s"  %
                        (old_slide_index, slide_index))

            comments_text = " ".join(
                [c.content for c in PictureComment.getComments(slide.count)])
            tags_text = " ".join(
                [t.name_ref.name for t in Tag.all().filter('count = ', slide.count)])
            template_values = {
                'slide': slide,
                'picture_comments': comments_text,
                'picture_tags': tags_text,

                'count_index':      slide.count,
                'prev_index':       prev_index,
                'current_index':    dateOrderIndex,
                'next_index':       self.get_next_index(index),
                'newest_index':     newest_index,
                'random_index':     random.randint(0, highest_picture_index()),

                'tags':             TagCloudHandler.get_cloud_tags(),

                'url_linktext':     url_linktext,
                'url':              url,
                'user':             user,
                'admin_flag':       admin_flag,
                'welcome_text':     welcome_text,
                'thedate':          slide.datetime,
                'blob_upload_url':  blobstore.create_upload_url('/blobupload'),
            }
            template_text = render_template_text('navigate_new.html', template_values)
            self.write_output(template_text)
        except OverQuotaError as oqe:
            template_text = render_template_text('over_quota.html', {})
            self.write_output(template_text)
            return

class CarouselHandler(FilmstripHandler):
    def get(self, index=None, num_pics=10):
        if index is not None:
            index = int(float(index))

        num_pics = int(float(num_pics))

        pis = self.get_filmstrip_indices(num_pics, index)
        template_text = render_template_text(
                            'carousel.html',
                            {
                                'current_index': index,
                                'newest_index': highest_picture_index(),
                                'carousel_slides': pis,
                                'dont_lazyload': True,
                            }
                        )
        self.write_output(template_text)

class ExivByIndexHandler(RequestHandlerParent):
    def get(self):
        index = self.get_index_from_request(check_bounds=True)
        picture_index = PictureIndex.get(index=index)
        exivTags = "<pre>%s</pre>" % pformat(picture_index.pix_ref.getExivTags())
        try:
            self.write_output(exivTags)
        except:
            outtext = "error in exiv handler for index %d, %s" % (
                        index, str(exivTags["Image Model"]))
            self.write_output(outtext)

class UpdateTagCountsHandler(RequestHandlerParent):
    def get(self):
        UniqueTagName.updateTagCounts()
        tag_counts = UniqueTagName.getTagCounts()
        self.write_output(pformat(tag_counts))

class TagCloudHandler(RequestHandlerParent):
    @classmethod
    def get_cloud_tags(cls, shuffle=True):
        """ Get the UniqueTagName to display, breaking them out into a vanilla
        list from the Query object returned by .all(), and giving them a
        logorithmic font size for the tag cloud.

        Note that an actual math.log call was too expensive for the hundreds of
        tags.
        """
        unique_tags = memcache.get('cloud_tags')

        if unique_tags is None:
            unique_tags = []
            utns = UniqueTagName.all()
            for utn in utns:
                tag = {'name': utn.name, 'fontsize': utn.fontsize()}
                unique_tags.append(tag)
            if shuffle:
                random.shuffle(unique_tags)
            memcache_status = memcache.set('cloud_tags', unique_tags)
            if memcache_status:
                logging.debug('wrote cloud tags to memcache')
            else:
                logging.debug('cloud tags to memcache write FAILED')
        else:
            logging.debug('got cloud tags via memcache')

        return unique_tags

    def get(self):
        unique_tags = TagCloudHandler.get_cloud_tags()
        text = render_template_text('tag_cloud.html', {'tags': unique_tags})
        self.write_output(text)

class TagsByIndexHandler(RequestHandlerParent):
    def get(self):
        count = self.get_index_from_request('count', check_bounds=True)
        tagNames = Tag.getTagNames(count)
        self.write_output(tagNames)

class TagsByNameHandler(RequestHandlerParent):
    def get(self):
        name = self.request.get('name')
        tags = Tag.getIndicesByName(name)
        self.write_output(tags)

class CommentByIndexHandler(RequestHandlerParent):
    def getText(self, count):
        comments = PictureComment.getComments(count)

        outText = ""
        for comment in comments:
            outText += "<em>%s</em>" % comment.content
        return outText

    def get(self):
        self.write_output(self.getText())

class DateByIndexHandler(RequestHandlerParent):
    def getText(self, count, is_compact=False):
        pictureIndex = PictureIndex.get(index=count, by_date=False)
        if pictureIndex is not None:
            if pictureIndex.pix_ref is not None:
                picture = pictureIndex.pix_ref
                date = picture.getDate(is_compact=is_compact)
            else:
                date = None
        else:
            date = None
        return date

    def get(self):
        date = self.getText()
        if date is not None:
            self.write_output("<small>" + date + "</small>")
        else:
            self.error(404)

class OrphanHandler(RequestHandlerParent):
    orphan_blobs = []
    orphan_pictures = []

    def get_orphan_blobs(self):
        self.orphan_blobs = []
        blobs = blobstore.BlobInfo.all().run()
        for blob in blobs:
            ref_count = Picture.all().filter(
                            "blobStorePictureKey =", blob.key()).count(1)
            if not ref_count:
                self.orphan_blobs.append(blob)
                logging.info("OphanHandler: %s Ophan blob %s" % (ref_count, blob))

    def adopt_orphan_pictures(self, limit):
        pictures = Picture.all().run()
        self.orphan_pictures = []
        good_count = 0

        count = highest_index_value(cn_hpi , 'count')
        dateOrderIndex = highest_index_by_date()

        iorphan = 0
        for picture in pictures:
            if len(self.orphan_pictures) < limit:
                ref_count = PictureIndex.all(
                            ).filter("pix_ref =", picture.key()).count(1)
                if not ref_count:
                    iorphan += 1
                    logging.info('count is %s, count + iorphan is %s' % (count, count+iorphan))
                    dateOrderString = get_date_order_string(count=count+iorphan,
                                                            rawDate=picture.getDateRaw())
                    pictureIndex = PictureIndex.make_picture_index(
                                       picture,
                                       count + iorphan,
                                       dateOrderIndex + iorphan,
                                       dateOrderString)
                    pictureIndex.put()
                    self.orphan_pictures.append(picture)
                    logging.info(
                        "OphanHandler.get_orphan_pictures: ref_count=%s, "
                        "good_count=%s, orphan_count=%s, Ophan picture %s" % (
                        ref_count, good_count, len(self.orphan_pictures), picture))
                else:
                    good_count +=1

    def get_orphan_pictures(self, offset=0, limit=25000):
        pictures = Picture.all().run(offset=offset)
        self.orphan_pictures = []

        good_count = 0

        for picture in pictures:
            if len(self.orphan_pictures) < limit:
                ref_count = PictureIndex.all(
                            ).filter("pix_ref =", picture.key()).count(1)
                if not ref_count:
                    self.orphan_pictures.append(picture)
                    logging.info(
                        "OphanHandler.get_orphan_pictures: ref_count=%s, "
                        "good_count=%s, orphan_count=%s, Ophan picture %s" % (
                        ref_count, good_count, len(self.orphan_pictures), picture))
                else:
                    good_count +=1

class DeleteOrphanBlobsHandler(OrphanHandler):
    """Delete orphan blobs"""
    def get(self):
        try:
            self.get_orphan_blobs()
        except DeadlineExceededError as dee:
            self.write_output(
                "Deadline Exceeded: %s orphan blobs to delete." %
                (len(self.orphan_blobs)))
        finally:
            for blob in self.orphan_blobs:
                blob.delete()
            return

class DeleteOrphanPicturesHandler(OrphanHandler):
    """Delete orphan pictures"""
    def get(self):
        try:
            self.get_orphan_pictures()
        except DeadlineExceededError as dee:
            self.write_output(
                "Deadline Exceeded: %s orphan pictures to delete." %
                (len(self.orphan_pictures)))
        finally:
            for picture in self.orphan_pictures:
                logging.info('deleting picture %s' % picture)
                picture.delete()
            return

class CountOrphanBlobsHandler(OrphanHandler):
    """Display which blobs are orphans"""
    def get(self):
        try:
            self.get_orphan_blobs()
            msg = "%d Orphan blobs" % (len(self.orphan_blobs))
            logging.info(msg)
            self.write_output(msg)
        except DeadlineExceededError as dee:
            self.write_output(
                "Deadline Exceeded: %s orphan blobs found so far." %
                (len(self.orphan_blobs)))
            return

class CountOrphanPicturesHandler(OrphanHandler):
    """Display which Picture entities are orphans"""
    def get(self, offset=0):
        try:
            self.get_orphan_pictures()
            msg = "%d Orphan pictures with offset %s" % (len(self.orphan_pictures), offset)
            logging.info(msg)
            self.write_output(msg)
        except DeadlineExceededError as dee:
            self.write_output(
                "Deadline Exceeded: %s orphan pictures found so far." %
                (len(self.orphan_pictures)))
            return

class AdoptOrphanPicturesHandler(OrphanHandler):
    """Create which Picture entities are orphans"""
    def get(self, limit=1000):
        try:
            self.adopt_orphan_pictures(limit)
            msg = "%d Orphan pictures adopted" % (len(self.orphan_pictures))
            logging.info(msg)
            self.write_output(msg)
        except DeadlineExceededError as dee:
            self.write_output(
                "Deadline Exceeded: %s orphan pictures adopted so far." %
                (len(self.orphan_pictures)))
            return

class OrphanBlobsHandler(OrphanHandler):
    """Display an orphan blob"""
    def get(self, pic_to_show=0):
        self.get_orphan_blobs()
        random.shuffle(self.orphan_blobs)
        image = self.orphan_blobs[int(pic_to_show)].open().read()

        self.response.headers['Content-Type'] = "image/jpg"
        self.response.out.write(str(image))

        msg = "%d Orphan blobs" % (len(self.orphan_blobs))
        logging.info(msg)

class OrphanPicturesHandler(OrphanHandler):
    """Display an orphan picture"""
    def get(self, pic_to_show=0):
        self.get_orphan_pictures(limit=5)

        self.response.headers['Content-Type'] = "image/jpg"
        picture = self.orphan_pictures[int(pic_to_show)]
        self.write_output(picture.getImage())

        msg = "%d Orphan pics" % (len(self.orphan_pictures))
        logging.info(msg)

class FlushMemcacheHandler(RequestHandlerParent):
    """Flush the memcache and redirect to the homepage"""
    def get(self, url=None):
        memcache.flush_all()
        url = self.request.get('redirect')
        if url:
            self.redirect(url)
        else:
            self.redirect('/')

class MetaDataHandler(RequestHandlerParent):
    """Return a JSON object of all the image's metadata"""
    def get(self, added_order_index=None):
        if added_order_index is None:
            added_order_index = self.get_index_from_request('count', check_bounds=False)
            if added_order_index is None:
                added_order_index = 0
        added_order_index = int(added_order_index)

        picture_index = PictureIndex.get(added_order_index, by_date=False)

        comments = [str(c.content) for c in PictureComment.getComments(added_order_index)]
        tags = Tag.getTagNames(added_order_index)

        info = {
            'tags': tags,
            'url': 'http://surlyfritter.appspot.com/imgperm/%s' % added_order_index,
            'comments': comments,
        }
        if picture_index:
            info['picture_index_count'] = picture_index.count
            info['picture_index_date_order'] = picture_index.dateOrderIndex
            info['picture_index_date_order_string'] = picture_index.dateOrderString

        self.write_output("%s\n" % json.dumps(info))

class WriteBucket(RequestHandlerParent):
    """Test to demonstrate cloudstorage writes."""
    def get(self):
        filename = 'foo%s' % datetime.datetime.now().isoformat()
        gcs_filename = GCS_BUCKET + '/' +  filename
        gcs_file = gcs.open(gcs_filename, 'w')
        gcs_file.write('test text'.encode('utf-8'))
        gcs_file.close()
        blobstore_filename = '/gs' + gcs_filename
        gs_key = blobstore.create_gs_key(blobstore_filename)

class ListBucket(RequestHandlerParent):
    """List cloudstorage files."""
    def get(self):
        gcs_iterator = gcs.listbucket(GCS_BUCKET)
        logging.info("gcs_iterator %s" % gcs_iterator)
        items = []
        for item in gcs_iterator:
            logging.info("gcs_iterator item %s" % item)
            items.append(item)

        self.write_output("Done %s %s\n" % (gcs_iterator, pformat(items)))

class EmailHandler(InboundMailHandler):
    def post(self):
        """Transforms body to email request."""
        self.receive(mail.InboundEmailMessage(self.request.body))

    def upload_to_google_cloudstorage(self, filename, image):
        """Create a GCS file with GCS client lib.

        Args:
          filename: GCS filename.
          image: data to write

        Returns:
          The corresponding string blobkey for this GCS file.
        """
        # Create a GCS file with GCS client. Add a timestamp so the filename
        # won't get stomped.
        gcs_filename = "%s/%s%s" % (GCS_BUCKET,
                                    datetime.datetime.now().isoformat(),
                                    filename)

        logging.info("gcs_filename %s" % gcs_filename)
        gcs_file = gcs.open(gcs_filename,
                            'w',
                            content_type='image/jpeg')
        gcs_file.write(image)
        gcs_file.close()

        # Blobstore API requires extra /gs to distinguish against blobstore files
        blobstore_filename = '/gs' + gcs_filename
        logging.info("blobstore_filename %s" % blobstore_filename)

        # This blob_key works with blobstore APIs that do not expect a
        # corresponding BlobInfo in datastore
        gs_key = blobstore.create_gs_key(blobstore_filename)
        logging.info("gs key %s" % gs_key)
        return gs_key

    def receive(self, email, isBlobstore=BLOBSTORE_UPLOAD_DEFAULT):
        # Only accept email from authorized users:
        #
        isUserAuthorized = email.sender in AUTHORIZED_UPLOADERS
        if not isUserAuthorized:
            msg = ('Ignoring email from unauthorized user: %s' % email.sender)
            logging.info(msg)
            notification_email("Ignoring unauthorized email", msg)
            return

        # Bail out if there is not attachment:
        #
        if not hasattr(email, 'attachments'):
            logging.info('Ignoring email with no attachments from: %s' % email.sender)
            return

        if isinstance(email.attachments, tuple):
            attachments = [email.attachments]
        else:
            attachments = email.attachments

        images_size_sum = 0
        successful_picture_indices = []

        # Extract the subject, if there is one:
        #
        subj = None
        if hasattr(email, 'subject'):
            if email.subject != "":
                subj = email.subject

        # work with attachments as normal
        #
        for (name, image) in attachments:
            decoded_image = image.payload.decode(image.encoding)

            # Skip any image larger than MAX_IMAGE_UPLOAD_SIZE. And skip images
            # that push this transaction over MAX_TRANSACTION_SIZE. Skipping it
            # here prevents orphan blobs from being created:
            #
            image_size = len(decoded_image)
            images_size_sum += image_size
            if images_size_sum > MAX_TRANSACTION_SIZE:
                msg = ('EmailHandler.receive: email upload is '
                       'too large for the transaction. Skipping %s.' % name)
                logging.info(msg)
                notification_email(
                    "picture FAILURE overall transaction size caught in"
                    "EmailHandler",
                    msg)
                continue

            if image_size > MAX_IMAGE_UPLOAD_SIZE:
                msg = ('EmailHandler.receive: image "%s" is '
                       'too large. Skipping.' % name)
                logging.info(msg)
                notification_email("picture FAILURE caught in EmailHandler", msg)
                continue

            if isBlobstore:
                try:
                    #blob_key = self.make_blobstore_image(decoded_image)
                    blob_key = self.upload_to_google_cloudstorage(name, decoded_image)
                    image_for_picture = blob_key
                    logging.info("making blobstore image: %s" % blob_key)
                except Exception as err: # broad to avoid creating bad PictureIndexes
                    logging.info("upload_to_google_cloudstorage %s" % err)
                    continue
            else:
                image_for_picture = decoded_image

            pi = add_picture(image=image_for_picture, name=name, isBlobstore=isBlobstore)

            successful_picture_indices.append(pi)

            logging.info('EmailHandler:receive: Uploading picture %s received '
                         'in email from %s as %d with isBlobstore %s' %
                         (name,
                          email.sender,
                          highest_index_value(cn_hpi , 'count'),
                          isBlobstore))

            # If there is a subject, add it as a PictureComment
            #
            if subj:
                logging.info('Adding comment from email subject: %s' % subj)
                pictureComment = PictureComment()
                pictureComment.content = subj
                pictureComment.picture_index = highest_index_value(cn_hpi,
                                                                   'count')
                pictureComment.put()
            else:
                logging.info('email doesnt have subject')

        if len(successful_picture_indices) > 0:
            email_upload_summary(successful_picture_indices, subj)

#class TilesHandler(webapp.RequestHandler):
    #def get(self, z, x, y):
        #tile = '<img src="/static/tiles/%s/%s/%s.jpg"/>' % (z, x, y)
        #self.response.out.write(tile)

class NotFoundPageHandler(webapp.RequestHandler):
    def get(self):
        self.error(404)
        self.response.out.write('Page Not Found! <a href="/">Front page</a>')

class ReactHandler(webapp.RequestHandler):
    def get(self):
        text = render_template_text('react.html', [])
        self.response.out.write(str(text))

def real_main():
    application = webapp.WSGIApplication(
        [
            ('/listbucket',          ListBucket),
            ('/writebucketfile',     WriteBucket),
            ('/imgsrv/(.*)',         ImageServingUrl),
            ('/navold/(.+)',         NavigatePictures),
            ('/navold/(.+)/(.+)',    NavigatePictures),
            ('/nav',                 NavigatePicturesNew),
            ('/nav/',                NavigatePicturesNew),
            ('/nav/(.*)/(.*)',       NavigatePicturesNew),
            ('/nav/(.*)/',           NavigatePicturesNew),
            ('/nav/(.*)',            NavigatePicturesNew),
            ('/perm',                NavigatePicturesNew),
            ('/perm/',               NavigatePicturesNew),
            ('/perm/(.*)/(.*)',      NavigatePicturesNew),
            ('/perm/(.*)/',          NavigatePicturesNew),
            ('/perm/(.*)',           NavigatePicturesNew),
            ('/navperm',             NavigatePicturesNew),
            ('/navperm/',            NavigatePicturesNew),
            ('/navperm/(.*)/(.*)',   NavigatePicturesNew),
            ('/navperm/(.*)/',       NavigatePicturesNew),
            ('/navperm/(.*)',        NavigatePicturesNew),
            ('/(\d+)',               NavigatePicturesNew),
            ('/newpicture',          NavigatePicturesNew),
            ('/navigate',            NavigatePicturesNew),
            ('/n',                   NavigatePicturesNew),
            ('/navdate/(.*)',        NavigateByDateHandler),
            ('/imgdate/(.*)',        ImageByDateHandler),
            ('/img',                 ImageByIndexHandler),
            ('/img/',                ImageByIndexHandler),
            ('/img/(.*)',            ImageByIndexHandler),
            ('/imgperm',             ImageByOrderAddedHandler),
            ('/imgperm/',            ImageByOrderAddedHandler),
            ('/imgperm/(.*)',        ImageByOrderAddedHandler),
            ('/imgname/(.*)',        ImageByNameHandler),
            ('/tag/(.*)',            ImagesByTagHandler),
            ('/timejump/(.*)/(.*)',  TimeJumpHandler), # current_index, days
            ('/miri_is',             MiriTimeJumpHandler),
            ('/miri_is/',            MiriTimeJumpHandler),
            ('/miri_is/(.*)',        MiriTimeJumpHandler),
            ('/julia_is',            JuliaTimeJumpHandler),
            ('/julia_is/',           JuliaTimeJumpHandler),
            ('/julia_is/(.*)',       JuliaTimeJumpHandler),
            ('/linus_is',            LinusTimeJumpHandler),
            ('/linus_is/',           LinusTimeJumpHandler),
            ('/linus_is/(.*)',       LinusTimeJumpHandler),
            ('/same_age',            SameAgeJumpHandler),
            ('/same_age',            SameAgeJumpHandler),
            ('/same_age/',           SameAgeJumpHandler),
            ('/same_age/(.*)',       SameAgeJumpHandler),
            ('/side_by_side(.*)',    SideBySideHandler),
            #('/side_by_side/(.*)/(.*)', SideBySideHandler),
            #('/filmstrip/(.*)',      FilmstripHandler),
            #('/filmstrip',           FilmstripHandler),
            ('/carousel/(.*)/(.*)',  CarouselHandler),
            ('/carousel/(.*)',       CarouselHandler),
            ('/carousel/',           CarouselHandler),
            ('/carousel',            CarouselHandler),

            ('/',                         NavigatePicturesNew),
            ('/slideshow',                StartSlideShow),
            ('/addtag',                   AddTag),
            ('/addcomment',               AddComment),
            ('/addgreeting',              AddGreeting),
            ('/markfavorite',             MarkAsFavorite),
            ('/clearfavorites',           ClearFavorites),
            #('/tagdatechanges',           TagDateChanges),
            ('/favoritespage',            MakeFavoritesPage),
            ('/showuploadpage',           ShowUploadPage),
            ('/blobupload',               BlobUploadNewPicture),
            ('/blobview.*',               BlobViewPicture),
            ('/uploadpicture',            UploadNewPicture),
            ('/\d+\.jpg',                 ImageByJpgIndexHandler),
            ('/jpg.*',                    ImageByJpgIndexHandler),
            ('/imgbyindex',               ImageByIndexHandler),
            ('/exivbyindex',              ExivByIndexHandler),
            ('/datebyindex',              DateByIndexHandler),
            ('/tagsbyindex',              TagsByIndexHandler),
            ('/tagsbyname',               TagsByNameHandler),
            ('/imagesbytag',              ImagesByTagHandler),
            ('/tagcloud',                 TagCloudHandler),
            ('/updatetagcounts',          UpdateTagCountsHandler),
            ('/commentbyindex',           CommentByIndexHandler),
            ('/highestindex',             HighestIndexHandler),
            ('/setdateorderindex',        SetDateOrderIndexHandler),
            ('/fixdateorderindex',        FixDateOrderIndexHandler),
            ('/adddateorderstring',       AddDateOrderString),
            ('/getdateorderstring',       GetDateOrderString),
            ('/datebycount',              DateOrderIndexByCountHandler),
            ('/countbydate',              CountByDateOrderIndexHandler),
            ('/flush.*',                  FlushMemcacheHandler),
            ('/feeds/.*',                 FeedHandler),
            ('/_ah/mail/.*',              EmailHandler),
            ('/orphanblobs',              OrphanBlobsHandler),
            ('/orphanblobs/',             OrphanBlobsHandler),
            ('/orphanblobs/(.*)',         OrphanBlobsHandler),
            ('/orphanpictures',           OrphanPicturesHandler),
            ('/orphanpictures/',          OrphanPicturesHandler),
            ('/orphanpictures/(.*)',      OrphanPicturesHandler),
            ('/countorphanblobs',         CountOrphanBlobsHandler),
            ('/countorphanpictures',      CountOrphanPicturesHandler),
            ('/adoptorphanpictures/(.*)', AdoptOrphanPicturesHandler),
            ('/deleteorphanblobs',        DeleteOrphanBlobsHandler),
            ('/deleteorphanpictures',     DeleteOrphanPicturesHandler),
            ('/meta',                     MetaDataHandler),
            ('/meta/(.*)',                MetaDataHandler),
            ('/replaceimage',             ReplaceImageHandler),

            ('/recipes',                  RecipesHandler),
            ('/recipes/(.*)',             RecipesHandler),
            ('/pancakes',                 PancakesHandler),

            ('/react', ReactHandler),

            #('/tiles/(\d+)/(\d+)/(\d+).jpg', TilesHandler), # webgl experiment

            ('/.*',                       NotFoundPageHandler),
        ],
        debug=True
    )
    wsgiref.handlers.CGIHandler().run(application)

def profile_main():
    # This is the main function for profiling
    # We've renamed our original main() above to real_main()
    import cProfile, pstats
    prof = cProfile.Profile()
    prof = prof.runctx("real_main()", globals(), locals())
    print "<pre>"
    stats = pstats.Stats(prof)
    stats.sort_stats("cumulative")  # Or cumulative
    #stats.print_stats(80)  # 80 = how many to print
    # The rest is optional.
    stats.print_callees()
    import ipdb; ipdb.set_trace()
    stats.print_callers()
    print "</pre>"

if __name__ == "__main__":
    #profile_main()
    real_main()
