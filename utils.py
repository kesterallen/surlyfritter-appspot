
import logging
import os
from google.appengine.ext.webapp import template

from google.appengine.api import memcache

from DataModels import PictureIndex

cn_hpi = "highestPictureIndex"
cn_hpi_date = "highestPictureIndexByDate"

def render_template_text(fname, values, subdirectory='templates/surlyfritter'):
    this_dir = os.path.dirname(__file__)
    logging.info(this_dir)
    if subdirectory:
        this_dir = os.path.join(this_dir, subdirectory)
    logging.info(this_dir)
    template_fullname = os.path.join(this_dir, fname)
    logging.info(template_fullname)
    rendered_text = template.render(template_fullname, values)
    return rendered_text

def highest_index_value(memcache_name, field_name):
    index = memcache.get(memcache_name)
    if index is None:
        highest_pi = PictureIndex.all().order('-%s' % field_name).get()
        index = getattr(highest_pi, field_name) if highest_pi else 0
        memcacheStatus = memcache.set(memcache_name, index)
    return index

def highest_picture_index():
    return highest_index_by_date()

def highest_index_by_date():
    return highest_index_value(cn_hpi_date, 'dateOrderIndex')

