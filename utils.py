
import logging
import os
from google.appengine.ext.webapp import template

from google.appengine.api import memcache

from DataModels import PictureIndex

cn_hpi = "highestPictureIndex"
cn_hpi_date = "highestPictureIndexByDate"

def render_template_text(template_fname, values_to_insert):
    template_filename = os.path.join(os.path.dirname(__file__), template_fname)
    rendered_text = template.render(template_filename, values_to_insert)
    return rendered_text

def highest_index_value(memcache_name, field_name):
    index = memcache.get(memcache_name)

    if index is None:
        logging.info("Running highest picture index retrieve")
        highest_pi = PictureIndex.all().order('-%s' % field_name).get()
        if highest_pi:
            index = getattr(highest_pi, field_name)
        else:
            index = 0
        logging.info("highest picture index is {}".format(index))
        logging.debug("memcaching the highestPictureIndex {} for {}".format(index, memcache_name))
        memcacheStatus = memcache.set(memcache_name, index)
        if not memcacheStatus:
            logging.debug("memcaching failed in highestPictureIndex")
    else:
        logging.debug("memcache worked highestPictureIndex result for "
                      "memcache_name: %s, %s" %
                      (memcache_name, index))
    return index

def highest_picture_index():
    return highest_index_by_date()

def highest_index_by_date():
    return highest_index_value(cn_hpi_date, 'dateOrderIndex')

