#!/usr/bin/env python2
######################################################################
# Copyright (C) 2016 Richard Gay
# Copyright (C) 2011 Chris McCormick
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
######################################################################
import os
from sys import argv
from time import time
from email.message import Message
from email.mime.multipart import MIMEMultipart
from email.message import Message
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import mimetypes
from mailbox import mbox
import sqlite3
import re
import logging

######################################################################
# Config
######################################################################
MBOX_ENCODING="utf8"

verbose = False
counter = {}

skip_folders = ("spam", "trash")

logging.basicConfig(format='%(asctime)-15s %(name)s: %(message)s', level=logging.ERROR)

######################################################################
import sys
reload(sys)  # Reload does the trick!
sys.setdefaultencoding(MBOX_ENCODING)

uri_file_matcher = re.compile('.*/([^/]*)/RAW')

header_map = {# mapping mail header fields to database columns
		"To":   "to_list",
		"From": "sender_list",
		"Bcc":  "bcc_list",
		"Cc":   "cc_list",
		"Date": "date",
		"Internal-Date": "internal_date",
		"Reply-To":      "reply_to_list",
		"Message-Id":    "message_id",
		"Mime-Type":     "mime_type",
}

logger = logging.getLogger("k9db-to-mbox")

######################################################################
# Main Code
######################################################################

if len(argv) > 1:
	# create the mailbox to write to
	mboxroot = "rescued-" + str(int(time())) + ".mbox"

	# argument
	db_file = argv[1]
	attach_dir = db_file + "_att"

	# connect to the sqlite3 database
	db = sqlite3.connect(db_file)
	db.row_factory = sqlite3.Row
	cr = db.cursor()
	# get the names of all folders
	cr.execute('select * from folders')
	folders = dict([(f['id'], f['name']) for f in cr.fetchall()])
	# get all messages k9 knows about
	cr.execute('select * from messages')
	all_messages = cr.fetchall()

	# ['id', 'deleted', 'folder_id', 'uid', 'subject', 'date', 'flags', 'sender_list', 'to_list', 'cc_list', 'bcc_list', 'reply_to_list', 'html_content', 'text_content', 'attachment_count', 'internal_date', 'message_id', 'preview', 'mime_type']
	logger.info("Found %d messages", len(all_messages))
	for msg in all_messages:
		if msg['sender_list'] is None:
			logger.debug("Skipping message %s", msg['message_id'])
			continue
		folder = folders[msg['folder_id']]
		if folder.lower() in skip_folders:
			logger.debug("Skipping message in folder '%s'", folder)
			continue

		# separate logger for this e-mail
		mlogger=logging.getLogger("[%s] '%s'" % (folder, msg['subject']))

		mlogger.info("[%s] %s -> %s (%s) : %s", folder, msg["sender_list"], msg["to_list"], msg["date"], msg["subject"])

		# extract the name of the mbox we want to write to
		mboxname = os.path.join(mboxroot, folder)
		folder, mboxfile = os.path.split(mboxname)
		# if the hierarchy of folders doesn't exist yet, create it
		if not os.path.isdir(folder):
			os.makedirs(folder)
		# open the mbox pointing there
		m = mbox(mboxname)
		mid = msg["message_id"]
		# create a new email message to write to the mbox
		if msg["text_content"] and msg["html_content"] or msg['attachment_count']:
			mlogger.info("\t type: %s (%d attachments)", msg['mime_type'], msg['attachment_count'])
			fst,snd = msg["mime_type"].split('/',1) # e.g., "multipart/mixed"
			root = MIMEMultipart(snd)
			if msg['text_content']:
				text = MIMEText(msg["text_content"], _subtype="plain", _charset=MBOX_ENCODING)
				if msg["html_content"]:
					mlogger.warning("\t HTML content available (skipping)")
			elif msg['html_content']:
				text = MIMEText(msg['html_content'], _subtype="html",  _charset=MBOX_ENCODING)
				text.add_header('Content-Disposition', 'attachment', filename="body.html")
			root.attach(text)
		else:
			mlogger.info("\t ordinary message")
			root = Message()
			root.set_payload(msg["text_content"], MBOX_ENCODING)

		# retrieve the headers for this message and insert them
		cr.execute('select * from headers where message_id=%d' % msg['id'])

		headers = cr.fetchall()
		for header in headers:
			root[header['name']] = header['value'].encode(MBOX_ENCODING)
		# set further headers from 'msg' only if they're not already set
		# (to avoid duplicates)
		for header in header_map.keys():
			if not root.has_key(header):
				value = msg[header_map[header]]
				if value and value!='':
					root[header] = value

		# retrieve the attachments and add them to the message
		# ['id', 'message_id', 'store_data', 'content_uri', 'size', 'name', 'mime_type', 'content_id', 'content_disposition']
		cr.execute('select * from attachments where message_id=%d' % msg['id'])
		attachments = cr.fetchall()
		for a in attachments:
			t,st = a['mime_type'].split('/',1) # type and sub-type
			match = uri_file_matcher.match(a['content_uri'])
			if match:
				fname = os.path.join(attach_dir, match.group(1))
			else:
				mlogger.error("\t skipping not found attachment '%s'", a['content_uri'])
				continue

			mlogger.debug("\t adding attachment of type %s/%s (in %s)", t,st, fname)
			if t in ['image', 'application', 'text']:
				fp = open(fname, 'rb')
				if t == 'image':
					attach = MIMEImage(fp.read(),       _subtype=st, name=a['name'])
				elif t == 'application':
					attach = MIMEApplication(fp.read(), _subtype=st, name=a['name'])
				elif t == 'text':
					attach = MIMEText(fp.read(),        _subtype=st, _charset=MBOX_ENCODING)
				fp.close()
				# Define the image's ID as referenced above
				if a['content_id']!='':
					attach.add_header('Content-ID', a['content_id'])
				attach.add_header('Content-Disposition', a['content_disposition'], filename=a['name'])
				root.attach(attach)
			else:
				mlogger.error("\t  skipping unsupported attachment, type '%s'", a['mime_type'])
				for x in ['store_data', 'content_uri', 'size', 'name', 'mime_type', 'content_id', 'content_disposition']:
					mlogger.debug("\t      %s: %s", x, str(a[x]))

		# add the email we created to our mbox
		m.add(root)
		m.close()
		# accounting
		counter[mboxfile] = counter.get(mboxfile, 0) + 1

	logger.info("Wrote all messages:")
	for box in counter:
		logger.info("\t %s: %s mails", box, counter[box])
else:
	logger.error("Please supply the name of an K-9 SQLite3 database file")

