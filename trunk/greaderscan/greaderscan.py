#! /usr/bin/env python

import sys
import getopt
import urllib
import urllib2
import re
import opml
import feedparser
import datetime

USAGE="""Scan your Google Reader feeds for activity

This simple script first pulls your feed list from Google Reader, then 
walks through the list, polling each feed URL looking for the most 
recent post and dead feed links.  It spits out the list of feeds it 
finds that are dead, inactive, or old.

Usage: greaderscan.py [options] -e email@addres.com -p password [-o file.txt] ... 

Parameters:
-e      -- Gmail address
-p      -- Gmail password
-o      -- output file (defaults to STDOUT)

Options:
-h      -- help
-a		-- age (in days) to flag a feed as old (by default, 180)
-v      -- verbose (echos to STDOUT when also writing to file)
-d      -- debug (dumps more data when exception is thrown)

Example:  

greaderscan.py -v -e me@gmail.com -p secret -o olddeadfeedlist.txt 
"""

def usage():
	global USAGE
	print USAGE
	sys.exit(1)

LOGIN = ""
PASSWORD = ""
SOURCE = "GoogleReader Scanner"
VERBOSE = 0
OUTPUT = ""
OLDEST = 180
DEBUG = 0

google_url = 'http://www.google.com'
reader_url = google_url + '/reader'
login_url = 'https://www.google.com/accounts/ClientLogin'
opml_url = reader_url + '/subscriptions/export'
token_url = reader_url + '/api/0/token'
subscription_list_url = reader_url + '/api/0/subscription/list'
reading_url = reader_url + '/atom/user/-/state/com.google/reading-list'
read_items_url = reader_url + '/atom/user/-/state/com.google/read'
reading_tag_url = reader_url + '/atom/user/-/label/%s'
starred_url = reader_url + '/atom/user/-/state/com.google/starred'
subscription_url = reader_url + '/api/0/subscription/edit'
get_feed_url = reader_url + '/atom/feed/'

def get_SID():
	result = ""
	header = {'User-agent' : SOURCE}
	post_data = urllib.urlencode({ 'Email': LOGIN, 'Passwd': PASSWORD, 'service': 'reader', 'source': SOURCE, 'continue': google_url, })
	request = urllib2.Request(login_url, post_data, header)

	try:
		f = urllib2.urlopen( request )
		result = f.read()    
		return re.search('SID=(\S*)', result).group(1)

	except (KeyboardInterrupt, SystemExit):
		raise
		
	except:
		print 'Error logging in'
		sys.exit()
		

#get results from url
def get_results(SID, url):
	result = ""
	header = {'User-agent' : SOURCE}
	header['Cookie']='Name=SID;SID=%s;Domain=.google.com;Path=/;Expires=160000000000' % SID

	request = urllib2.Request(url, None, header)

	try:
		f = urllib2.urlopen( request )
		result = f.read()

	except (KeyboardInterrupt, SystemExit):
		raise

	except:
		print 'Error getting data from %s' % url

	return result

#get a token, this is needed for modifying to reader
def get_token(SID):
	return get_results(SID, token_url)

#get a specific feed.  It works for any feed, subscribed or not
def get_feed(SID, url):
	return get_results(SID, get_feed_url + url.encode('utf-8'))

#get a list of the users subscribed feeds
def get_subscription_list(SID):
	return get_results(SID, subscription_list_url)

#get a feed of the users unread items
def get_reading_list(SID):
	return get_results(SID, reading_url)

#get a copy of the OPML export
def get_OPML(SID):
	return get_results(SID, opml_url)

#get a feed of the users read items
def get_read_items(SID):
	return get_results(SID, read_items_url)

#get a feed of the users unread items of a given tag
def get_reading_tag_list(SID, tag):
	tagged_url = reading_tag_url % tag
	return get_results(SID, tagged_url.encode('utf-8'))

#get a feed of a users starred items/feeds
def get_starred(SID):
	return get_results(SID, starred_url)

#subscribe of unsubscribe to a feed
def modify_subscription(SID, what, do):
	url = subscription_url + '?client=client:%s&ac=%s&s=%s&token=%s' % ( login, do.encode('utf-8'), 'feed%2F' + what.encode('utf-8'), get_token(SID) )
	print url
	return get_results(SID, url)

#subscribe to a feed
def subscribe_to(SID, url):
	return modify_subscription(SID, url, 'subscribe')

#unsubscribe to a feed
def unsubscribe_from(SID, url):
	return modify_subscription(SID, url, 'unsubscribe')

def mywrite(str):
	global VERBOSE, OUTPUT
	
	if VERBOSE:
		sys.stdout.write(unicode(str).encode("utf-8") + "\n")
		
	if OUTPUT:
		OUTPUT.write(unicode(str).encode("utf-8") + "\n")

def check_feeds(SID, dt, parsed_opml):
	global OLDEST, DEBUG
	
	for item in parsed_opml:
		f_url = getattr(item, 'xmlUrl', None)
		if f_url:
			# Check for a redirected stream
			try:
				t_url = urllib2.urlopen(f_url)
				f_url = t_url.geturl()
				
			except urllib2.HTTPError as e:
				if e.code in (400, 401, 403, 404, 405, 406, 410):
					mywrite("DEAD FEED -- '%s' is no longer active:  %s" % (item.title, f_url))
				else:
					mywrite("ERROR -- '%s' threw a %s:  %s (HTTPError)" % (item.title, e.code, f_url))
				continue
					
			except urllib2.URLError as e:
				mywrite("ERROR -- '%s' didn't respond (URLError %s):  %s" % (item.title, e.reason, f_url))
				continue
			
			# parse it
			try:
				d = feedparser.parse(f_url)
			except (KeyboardInterrupt, SystemExit):
				raise
			except:
				mywrite("ERROR -- Manual review required on '%s':  %s (%s)" % (item.title, f_url, sys.exc_info()[0]))
			else:
				try:
					if getattr(d, 'updated', None):
						updated = datetime.date(d.updated[0], d.updated[1], d.updated[2])
					elif getattr(d.feed, 'updated_parsed', None):
						updated = datetime.date(d.feed.updated_parsed[0], d.feed.updated_parsed[1], d.feed.updated_parsed[2])
					elif getattr(d.entries[0], 'updated_parsed', None):
						updated = datetime.date(d.entries[0].updated_parsed[0], d.entries[0].updated_parsed[1], d.entries[0].updated_parsed[2])
					else:
						mywrite("ERROR -- Manual review required on '%s':  %s (date error)" % (item.title, f_url))
						if DEBUG:
							mywrite("%s" % d)
						continue

					age = (dt - updated).days
					if age > OLDEST:
						mywrite("OLD FEED -- '%s' was last updated %d days ago." % (item.title, age))

				except IndexError:
					mywrite("ERROR -- Manual review required on '%s':  %s (parsing error)" % (item.title, f_url))
					if DEBUG:
						mywrite("%s" % d)
						
				except (KeyboardInterrupt, SystemExit):
					raise
					
				except:
					mywrite("UNKNOWN ERROR  -- Manual review required on %s (%s)" % (f_url, sys.exc_info()[0]))
		else:
			# item is a container (label or tag), recurse
			check_feeds(SID, dt, item)

def main():
	global LOGIN, PASSWORD, VERBOSE, OUTPUT, OLDEST, DEBUG
	
	try:
		opts, args = getopt.getopt(sys.argv[1:], "hdvae:p:o:", ["help", "debug", "verbose", "age=", "email=", "password=", "output="])
	except getopt.error:
		usage()
		
	for opt, arg in opts:
		if opt in ("-h", "--help"):
			usage()
		elif opt in ("-v", "--verbose"):
			VERBOSE = 1
		elif opt in ("-d", "--debug"):
			DEBUG = 1
		elif opt in ("-a", "--age"):
			OLDEST = int(arg)
		elif opt in ("-e", "--email"):
			LOGIN = arg
		elif opt in ("-p", "--password"):
			PASSWORD = arg
		elif opt in ("-o", "--output"):
			try:
				OUTPUT = open(arg, "w")
				
			except (KeyboardInterrupt, SystemExit):
				raise
				
			except:
				print "Error opening output file"
				sys.exit(2)
			
	if not (LOGIN and PASSWORD):
		usage()
		
	if not OUTPUT:
		VERBOSE = 1

	SID = get_SID()
	check_feeds(SID, datetime.date.today(), opml.from_string(get_OPML(SID)))
	
	if OUTPUT:
		OUTPUT.close()

if __name__ == '__main__':
	main()
