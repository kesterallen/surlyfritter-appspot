#!/usr/bin/python
"""
Determine which pictureIndexes have been assigned dateOrderStrings and add one
to those who have not. Re-apply new dateOrderStrings as needed (e.g. if a
picture older than the current photo has been added).  
"""

import optparse 
import os
import pickle
from pprint import pprint
import re
import subprocess
import sys
import time
import requests

options = None

def flush_memcache():
    if options.verbose:
        print "flushing memcache"
    requests.get(get_url('/flush'))

def get_url(url_suffix):
    url = "%s%s" % (options.site, url_suffix)
    if options.verbose:
        print url
    return url

def get_date_orders():
    # Load the date_order string info that has already been downloaded, and
    # extract the counts that have already been done:
    #
    if options.force:
        date_orders = []
        done_counts = []
    else:
        if os.path.isfile(options.pickle_file):
            date_orders = pickle.load(open(options.pickle_file)) 
        else:
            date_orders = []
        # just to be safe, ensure the sort by count is correct
        date_orders.sort(key=lambda x: x[1])
        done_counts = [int(date_order[1]) for date_order in date_orders]

    # Extract the dateOrderString fields from the site for new count indicies:
    #
    for i in range(int(options.start), int(options.end)+1):
        if i in done_counts:
            if options.verbose:
                print 'already have dateString for %d' % i
            continue

        r = requests.get(get_url("/getdateorderstring?index=%d" % i))
        if r.status_code == 200:
            re_match = re.search(
                            r'^date order string is ([\d:]+ [\d:]+) (\d+)', 
                            r.text)
            date_order = [re_match.group(1), re_match.group(2)]
            print 'getting datestring for count index %d: %s' % (i, date_order)
            date_orders.append(date_order)
            time.sleep(options.pause_seconds)
        else:
            print "Get date order string for %s failed" % i

    # just to be safe, ensure the sort by count is correct
    date_orders.sort(key=lambda x: x[1])

    # If the date is the default date (no evix data), use the (next picture
    # with a date)'s date instead:
    #
    for i in reversed(range(len(date_orders))):
        if date_orders[i][0] == options.default_date:
            print "GRABBING NEXT PICTURE'S DATE -- DEFAULT DATE DETECTED"
            date_orders[i][0] = date_orders[i+1][0]
        # TODO need to handle the last-item-doesn't-have-a-date case

    # Sort by date:
    #
    date_orders.sort()
    return date_orders

def setDateIndicies(date_orders, old_date_orders):
    # Print the update command, and if specified, actually do the update of
    # the site's real ordering:
    #
    for idate_orders, date_order in enumerate(date_orders):
        count = date_order[1]

        # Check the length to avoid an IndexError:
        #
        if idate_orders < len(old_date_orders) and \
           date_order == old_date_orders[idate_orders]:
            if options.verbose:
                print(
                    "Skipping unchanged PictureIndex: "
                    "count %s idate_orders %s" % (count, idate_orders))
            continue

        url = '/setdateorderindex?count=%s&dateorderindex=%s' % (
               count, idate_orders)
        if options.verbose:
            print "setting count %s to dateOderIndex %s for %s with %s" % (
                    count, idate_orders, date_order, url)

        if options.changeIndices:
            try:
                requests.get(get_url(url))
            except requests.RequestException as err:
                print "error running: %s, %s" % (url, err)
            time.sleep(options.pause_seconds)
        else:
            get_url(url) # prints the url

def parse_options():
    parser = optparse.OptionParser()
    parser.add_option(
        "-s", "--start", 
        type='int',
        default=0,
        help="start PictureIndex.count value")
    parser.add_option(
        "-e", "--end",
        type='int',
        help="end PictureIndex.count value")
    parser.add_option(
        "-f", "--force",
        action="store_true",
        default=False,
        help="re-download the date strings, regardless of if they are "
             "already saved locally")
    parser.add_option(
        "-c", "--changeIndices",
        action="store_true",
        default=False,
        help="actually change the online PictureIndex objects")
    parser.add_option(
        "-p", "--pause_seconds",
        type='float',
        default=0.5,
        help="Amount of time (sec) to pause between url gets.")
    parser.add_option(
        "-v", "--verbose",
        default=False,
        action="store_true",
        help="Verbosity flag.")
    parser.add_option(
        "--site",
        default="http://surlyfritter.appspot.com",
        help="Base URL of the picture site.")
    parser.add_option(
        "--pickle_file",
        default='dateOrders.pickle',
        help="The local pickle file to cache the date data in.")
    parser.add_option(
        "--default_date",
        default='2007:10:26 05:30:00',
        help="The default date pictures without exiv data are assigned to."
             "Should match DataModels.PictureIndex.defaultDate.")

    global options
    (options, args) = parser.parse_args()
    options.pause_seconds = float(options.pause_seconds)

    # Get the correct end index if it isn't specified:
    #
    if options.end is None:
        r = requests.get(get_url("/highestindex"))
        re_match = re.search(
                       r'highest count is (\d+) highest '
                           'date-ordered index is (\d+)',
                       r.text)
        options.end = re_match.group(1)

    print "running from count index %s to %s" % (options.start, options.end)

def main():
    parse_options()

    # Get the new correct date orders:
    #
    flush_memcache()
    date_orders = get_date_orders()

    # Get the old ones, if they exist:
    #
    if os.path.isfile(options.pickle_file):
        if options.verbose:
            print "Loading %s" % options.pickle_file
        old_date_orders = pickle.load(open(options.pickle_file))
    else:
        old_date_orders = []

    flush_memcache()
    setDateIndicies(date_orders, old_date_orders)

    # Save off the new correct date order data if updates have been made:
    #
    #import ipdb; ipdb.set_trace()
    if options.changeIndices:
        if options.verbose:
            print "Saving %s" % options.pickle_file
            print date_orders
        pickle.dump(date_orders, open(options.pickle_file, 'w'))

    flush_memcache()

if __name__ == "__main__":
    main()
