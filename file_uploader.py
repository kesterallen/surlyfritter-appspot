"""Script to upload groups of images to surlyfritter.com."""

import re
import sys
import time
import requests

DEBUG = False

class SurlyfritterImage:
    """
    Class to encapsulate the image/location of the image, and provide a method
    to submit the object to surlyfritter.
    """
    UPLOAD_URL = 'http://www.surlyfritter.com/showuploadpage'

    def __init__(self, fname):
        """Simple constructor."""
        self.fname = fname

    def submit(self):
        """Submit the SurlyfritterImage with a POST request to surlyfritter"""

        # Get BlobUploader URL
        response = requests.get(SurlyfritterImage.UPLOAD_URL)
        form_action_url = re.findall(r'form action="(.*?)"', response.text)[0]

        with open(self.fname, 'rb') as image_fh:
            files = {'file': image_fh}
            data = {}
            response = requests.post(form_action_url, files=files, data=data)
            response.raise_for_status()

    def __repr__(self):
        return "{0.fname}".format(self)

def main(img_fnames):
    """
    For a given list of images, make SurlyfritterImage instances and submit
    them to surlyfritter.
    """
    images = []
    print("Loading {} images".format(len(img_fnames)))
    for fname in img_fnames:
        image = SurlyfritterImage(fname)
        images.append(image)
    print("Loading complete")

    succeeded = []
    failed = []

    for i, image in enumerate(images):
        msg_sfx = "{} / {} {}".format(i+1, len(images), image)
        SKIP_LATER_THAN = 0 # TODO
        if i < SKIP_LATER_THAN: # tweak this for debugging
            print("skipping", msg_sfx)
            continue
        else:
            print("posting ", msg_sfx)

        try:
            image.submit()
            succeeded.append(image.fname)
        except requests.exceptions.HTTPError:
            failed.append(image.fname)
        if not DEBUG:
            time.sleep(60)

    requests.get('http://www.surlyfritter.com/flush')

    if succeeded:
        print("\nUploaded successfully:\n\t{}".format("\n\t".join(succeeded)))
    if failed:
        print("\n\nFailed:\n\t{}".format("\n\t".join(failed)))

if __name__ == '__main__':
    main(sys.argv[1:])
