
import logging
from google.appengine.ext import webapp

from DataModels import (Picture, PictureIndex, Greeting, UserFavorite,
                        PictureComment, UniqueTagName, Tag, str_to_dt)
from utils import highest_picture_index

class RequestHandlerParent(webapp.RequestHandler):
    """
    This parent class encapsulates extracting the index value from the HTTP
    request.
    """

    def write_output(self, content):
        """
        The self.response.out.write requires str inputs. Encapsulating that
        here along with unicode .
        """
        try:
            self.response.out.write(str(content))
        except (AssertionError, UnicodeEncodeError) as err:
            logging.debug("content is: \n%s\n err is %s", content, err)
            mangled_content = content.encode('ascii', 'ignore')
            logging.debug("mangled content is: \n%s" % mangled_content)
            self.response.out.write(mangled_content)

    def get_index_from_request(self, fieldname="index", check_bounds=False):
        index_string = self.request.get(fieldname)
        index = self.get_index(index_string, check_bounds)
        return index

    def validate_index(self, index, check_bounds):
        if index is None:
            imgindex = self.get_index_from_request(index, check_bounds=check_bounds)
            if not imgindex:
                imgindex = highest_picture_index()
        else:
            try:
                imgindex = int(index)
            except:
                imgindex = highest_picture_index()
                logging.debug("Can't convert %s to an int. Using %s instead", 
                              index, imgindex)
        return imgindex

    def get_index(self, index_string, check_bounds=True):
        try:
            index = int(index_string)
        except:
            logging.debug("Can't convert %s to an int. Using 0.", index_string)
            index = 0

        if check_bounds:
            highest = highest_picture_index()
            if index > highest:
                index = highest
            if index < 0:
                index = 0

        return index

