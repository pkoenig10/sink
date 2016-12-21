#!/usr/bin/env python

import os.path
import argparse
import getpass
import re
import hashlib
import cookielib
import urllib
import urllib2
import urlparse
import json
import webbrowser
import SimpleHTTPServer
import SocketServer
import threading
import shelve
import warnings
warnings.simplefilter('ignore', UserWarning)

from bs4 import BeautifulSoup
import gdata.contacts.data
import gdata.contacts.client
import gdata.gauth
from fuzzywuzzy import fuzz
from fuzzywuzzy import process


# Command descriptions
DESCRIPTION = '''\
Sink is a utility that uses Facebook profile pictures to provide high resolution photos for your Google contacts. \
Sink links each of your Google contacts with their Facebook profile and stores those links to allow for quick updates. \
To learn more about the commands read their help message.'''
UDPATE_DESCRIPTION = '''\
This command updates photos for your Google contacts by using your saved links. \
This command will create links for all contacts without links. \
A link will be automatically created if the contact's name and a Facebook friend name are a close enough match, otherwise you will be prompted to manually create the link. \
To see more detailed instructions run this command.'''
EDIT_DESCRIPTION = '''\
This command interactively edits saved links.
To see more detailed instructions run this command.'''
DELETE_DESCRIPTION = '''\
This command deletes all Google contact photos provided by Sink. \
This command can also delete all saved links.'''

# Instructions
UPDATE_INSTRUCTIONS = '''\
Each unlinked Google contact's name will be displayed along with list of suggested Facebook friends.\n\
You will be presented with a prompt. There are three options.\n\
  1. Type the list number of a suggested Facebook friend and press Enter to create a link with that friend.\n\
  2. Type a name and press Enter to perform another search of Facebook friends.\n\
     This is helpful if a contact's name does not closely match their Facebook name.\n\
  3. Press Enter without typing anything to ignore the contact.\n\
     Sink will ignore this contact during updates.'''
EDIT_INSTRUCTIONS = '''\
You will be presented with a name prompt.  Type the name of the Google contact you wish to edit and press Enter.  Press Enter without typing anything to exit.\n\
If the contact exists, their name will be displayed along with list of suggested Facebook friends.\n\
You will be presented with a prompt. There are three options.\n\
  1. Type the list number of a suggested Facebook friend and press Enter to create a link with that friend.\n\
  2. Type a name and press Enter to perform another search of Facebook friends.\n\
     A link will be automatically created if the search name and a Facebook friend name are a close enough match.\n\
     This is helpful if a contact's name does not closely match their Facebook name.\n\
  3. Press Enter without typing anything to ignore the contact.\n\
     Sink will ignore this contact during updates.'''

# Default arguments
PORT = 7465
SCORE_THRESHOLD = 100
MATCH_LIMIT = 5
RETRIES = 3

# Shelf keys
TOKEN = 'token'
USERNAME = 'username'
PASSWORD = 'password'
LINKS = 'links'
CHECKSUMS = 'checksums'


class Facebook:
    base_url = 'https://m.facebook.com'
    full_base_url = 'https://www.facebook.com'
    graph_api_picture = 'https://graph.facebook.com/%s/picture?height=720&width=720&redirect=false'
    friend_id_regex = r'fb://profile/(\d*)'

    def __init__(self, shelf):
        cookie_jar = cookielib.CookieJar()
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookie_jar))
        login_url = self.base_url + '/login/'
        username = shelf[USERNAME] if USERNAME in shelf else None
        password = shelf[PASSWORD] if PASSWORD in shelf else None
        while(True):
            if username is None:
                username = raw_input("Facebook username: ")
            if password is None:
                password = getpass.getpass("Facebook password: ")
            data = urllib.urlencode({'email':username, 'pass':password})
            request = urllib2.Request(login_url, data)
            response = self.opener.open(request)
            if response.geturl().split('?')[0] != login_url:
                break
            print "Incorrect login. Try again."
            username = None
            password = None
        shelf[USERNAME] = username
        shelf[PASSWORD] = password
        self.home_soup = BeautifulSoup(response.read(), 'html.parser')

    def _open(self, url):
        request = urllib2.Request(url)
        response = self.opener.open(request)
        return response.read()

    def _open_soup(self, url):
        return BeautifulSoup(self._open(url), 'html.parser')

    def _open_json(self, url):
        return json.loads(self._open(url))

    def get_profile_path(self):
        for link in self.home_soup.find_all('a'):
            if link.contents[0] == 'Profile':
                return link.get('href').split('?')[0]

    def get_friends(self):
        friends = {}
        friends_base_path = self.get_profile_path() + '/friends'
        friends_path = friends_base_path
        has_next = True
        while(has_next):
            has_next = False
            friends_soup = self._open_soup(self.base_url + friends_path)
            for link in friends_soup.find_all('a'):
                href = link.get('href')
                if href is None:
                    continue
                elif 'fref=fr_tab' in href:
                    delim = '&' if 'profile.php' in href else '?'
                    friends[unicode(href.split(delim)[0])] = unicode(link.contents[0])
                elif friends_base_path in href:
                    friends_path = href
                    has_next = True
                    break
        return friends

    def get_profile_picture(self, friend_url, friend):
        profile_html = self._open(self.full_base_url + friend_url)
        friend_id = re.search(self.friend_id_regex, profile_html).group(1)
        graph_api_json = self._open_json(self.graph_api_picture % friend_id)['data']
        if graph_api_json['is_silhouette']:
            return None
        return urllib.urlretrieve(graph_api_json['url'])[0]


class GoogleContacts:
    client_id = '552213042372-tf77q58ch6t6o6tp3s40d66pqeumg10v'  
    client_secret = 'mQyQpDQgjaZ5Leh8SjKLXu5y'
    scope = 'https://www.google.com/m8/feeds'
    user_agent = ''
    port = PORT

    def __init__(self, shelf):
        self.client = gdata.contacts.client.ContactsClient()
        if TOKEN not in shelf:
            shelf[TOKEN] = self._get_token()
        token = shelf[TOKEN]
        token.authorize(self.client)

    def _get_token(self):
        server = SocketServer.TCPServer(('localhost', self.port), self._OAuthResponseHandler)
        server_thread = threading.Thread(target=server.handle_request)
        server_thread.daemon = True
        server_thread.start()
        token = gdata.gauth.OAuth2Token(client_id=self.client_id, client_secret=self.client_secret, scope=self.scope, user_agent=self.user_agent)
        webbrowser.open(token.generate_authorize_url(redirect_uri='http://localhost:%d' % self.port))
        server_thread.join()
        server.server_close()
        token.get_access_token(server.code)
        return token

    def get_contacts(self):
        contacts = {}
        query = gdata.contacts.client.ContactsQuery(max_results=25000)
        feed = self.client.GetGroups()
        for group in feed.entry:
            if group.system_group and group.system_group.id == 'Contacts':
                query.group = group.id.text
                break
        feed = self.client.GetContacts(q=query)
        for contact in feed.entry:
            if contact.name and contact.name.full_name:
                contacts[contact.id.text.replace('base', 'full')] = contact.name.full_name.text
        return contacts

    def update_photo(self, contact_url, picture):
        contact = self.client.GetContact(contact_url)
        media = gdata.data.MediaSource(file_path=picture, content_type='image/jpeg')
        self.client.ChangePhoto(media, contact)

    def delete_photo(self, contact_url):
        contact = self.client.GetContact(contact_url)
        self.client.DeletePhoto(media, contact)

    class _OAuthResponseHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
        html = '''\
<!DOCTYPE html>
<html>
<head>
<title>Sink</title>
</head>
<body style="margin:0;">
<div style="background-color:#f1f1f1; height:60px;"></div>
<center>
<p style="font-family:Arial, sans-serif; font-size:1.2em; margin:1.5em 0px">Sink permission granted</p>
<p style="font-family:Arial, sans-serif; font-size:1em; margin:1em 0px">Please close this page.</p>
</center>
</body>
</html>'''

        def do_GET(self):
            query = urlparse.urlparse(self.path).query
            params = urlparse.parse_qs(query)
            self.server.code = params['code'][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(self.html)

        def log_message(self, format, *args):
            pass


class Sink:
    def __init__(self, shelf):
        self.shelf = shelf
        self.links = self.shelf[LINKS] if LINKS in shelf else {}
        self.checksums = self.shelf[CHECKSUMS] if CHECKSUMS in shelf else {}
        print "Authorizing Google..."
        self.google = GoogleContacts(shelf)
        print "Getting Google contacts..."
        self.contacts = self.google.get_contacts()
        print "%d contacts" % len(self.contacts)
        print "Authorizing Facebook..."
        self.facebook = Facebook(shelf)
        print "Getting Facebook friends..."
        self.friends = self.facebook.get_friends()
        print "%d friends" % len(self.friends)

    def update(self, update_ignored=False, auto_only=False, score_threshold=SCORE_THRESHOLD, match_limit=MATCH_LIMIT, retries=RETRIES):
        self._update_links(update_ignored, auto_only, score_threshold, match_limit)
        self._update_photos(retries)

    def edit(self, score_threshold=SCORE_THRESHOLD, match_limit=MATCH_LIMIT):
        self._edit_links(score_threshold, match_limit)

    def delete(self, delete_links=False, retries=RETRIES):
        self._delete_photos(retries)
        if delete_links:
            self._delete_links()

    def _update_photos(self, retries):
        print "Updating photos..."
        for contact_url in self.links:
            friend_url = self.links[contact_url]
            if friend_url is not None:
                picture = self.facebook.get_profile_picture(friend_url, self.friends[friend_url])
                if picture is None:
                    print "NO PICTURE: " + self.contacts[contact_url]
                    continue
                checksum = hashlib.md5(open(picture).read()).hexdigest()
                if contact_url in self.checksums and self.checksums[contact_url] == checksum:
                    print "UNCHANGED: " + self.contacts[contact_url]
                elif self._retry(lambda: self.google.update_photo(contact_url, picture), retries):
                    print "UPDATED: " + self.contacts[contact_url]
                    self._set_checksum(contact_url, checksum)
                else:
                    print "FAILED: " + self.contacts[contact_url]

    def _delete_photos(self, retries):
        print "Deleting photos..."
        self._clean_links()
        for contact_url in self.links:
            if self._retry(lambda: self.google.delete_photo(contact_url), retries):
                print "SUCCESS: " + self.contacts[contact_url]
            else:
                print "FAILURE: " + self.contacts[contact_url]

    def _clean_links(self):
        for contact_url in self.links.keys():
            if contact_url not in self.contacts or (self.links[contact_url] is not None and self.links[contact_url] not in self.friends):
                del self.links[contact_url]
                del self.checksums[contact_url]

    def _update_links(self, update_ignored, auto_only, score_threshold, match_limit):
        print "Updating links..."
        self._clean_links()
        unlinks = []
        for contact_url in self.contacts:
            if contact_url not in self.links or (update_ignored and self.links[contact_url] is None):
                matches = self._get_matches(self.contacts[contact_url], match_limit)
                if matches and matches[0][1] == score_threshold:
                    self._add_link(contact_url, matches[0][0])
                else:
                    unlinks.append(contact_url)
        if not auto_only and unlinks:
            print "\n" + UPDATE_INSTRUCTIONS
            for contact_url in unlinks:
                print
                self._get_link(contact_url, score_threshold, match_limit, True)

    def _edit_links(self, score_threshold=SCORE_THRESHOLD, match_limit=MATCH_LIMIT):
        self._clean_links()
        link_contacts = {self.contacts[contact_url]: contact_url for contact_url in self.links}
        print "\n" + EDIT_INSTRUCTIONS
        while(True):
            print
            name = raw_input("Name: ")
            if not name:
                break
            elif name not in link_contacts:
                print "Invalid name"
            else:
                contact_url = link_contacts[name]
                self._print_link(contact_url, "Status: ")
                self._get_link(contact_url, score_threshold, match_limit, False)

    def _delete_links(self):
        print "Deleting links..."
        if delete_links:
            self.links.clear()
            self._save_links()

    def _save_links(self):
        self.shelf[LINKS] = self.links

    def _add_link(self, contact_url, friend_url):
        self.links[contact_url] = friend_url
        self._save_links()
        self._print_link(contact_url)

    def _get_link(self, contact_url, score_threshold, match_limit, auto_match):
        name = self.contacts[contact_url]
        print name
        while(True):
            matches = self._get_matches(name, match_limit)
            if auto_match and matches and matches[0][1] == score_threshold:
                self._add_link(contact_url, matches[0][0])
                return
            for i, (friend_url, score) in enumerate(matches):
                print "  %d. %s (%d)" % (i + 1, self.friends[friend_url], score)
            while(True):
                command = raw_input("> ")
                if not command.isdigit() or (int(command) > 0 and int(command) <= match_limit):
                    break
            if not command:
                self._add_link(contact_url, None)
                return
            if command.isdigit():
                self._add_link(contact_url, matches[int(command) - 1][0])
                return
            name = command

    def _print_link(self, contact_url, prefix=""):
        friend_url = self.links[contact_url]
        if friend_url is None:
            print "%s%s IGNORED" % (prefix, self.contacts[contact_url])
        else:
            print "%s%s <- %s" % (prefix, self.contacts[contact_url], self.friends[friend_url])

    def _get_matches(self, name, match_limit):
        return process.extract(name, self.friends, scorer=fuzz.UWRatio, limit=match_limit)

    def _retry(self, func, retries):
        for retry in xrange(retries):
            try:
                func()
                return True
            except Exception:
                continue
        return False

    def _set_checksum(self, contact_url, checksum):
        self.checksums[contact_url] = checksum
        self._save_checksums()

    def _save_checksums(self):
        self.shelf[CHECKSUMS] = self.checksums


def main():
    args = parse_args()
    shelf = shelve.open(args.filename)
    sink = Sink(shelf)
    if args.command == 'update':
        sink.update(args.update_ignored, args.auto_only, args.score_threshold, args.match_limit, args.retries)
    elif args.command == 'edit':
        sink.edit(args.score_threshold, args.match_limit)
    elif args.command == 'delete':
        sink.delete_photos(args.delete_links, args.retries)

def parse_args():
    parser = argparse.ArgumentParser(prog='sink', description=DESCRIPTION, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    subparsers = parser.add_subparsers(dest='command', metavar='command')
    file_parser = argparse.ArgumentParser(add_help=False)
    file_parser.add_argument('filename', metavar='file', nargs='?', default='sinkshelf', type=filename, help='shelf database file to use')
    update_parser = argparse.ArgumentParser(add_help=False)
    update_parser.add_argument('-a', '--auto-only', dest='auto_only', action='store_true', help='skip all contacts not automatically linked')
    update_parser.add_argument('-i', '--update-ignored', dest='update_ignored', action='store_true', help='update all contacts previously ignored')
    delete_parser = argparse.ArgumentParser(add_help=False)
    delete_parser.add_argument('-l', '--delete-links', dest='delete_links', action='store_true', help='delete saved links')
    param_parser = argparse.ArgumentParser(add_help=False)
    param_parser.add_argument('-s', '--score', dest='score_threshold', metavar='SCORE', default=SCORE_THRESHOLD, type=score, help='score threshold to automatically link contacts')
    param_parser.add_argument('-m', '--matches', dest='match_limit', metavar='MATCHES', default=MATCH_LIMIT, type=int, help='number of matches to show when searching contacts')
    retry_parser = argparse.ArgumentParser(add_help=False)
    retry_parser.add_argument('-r', '--retries', dest='retries', metavar='RETRIES', default=RETRIES, type=int, help='number of times to retry updating photos before failing')
    update = subparsers.add_parser('update', parents=[file_parser, update_parser, param_parser, retry_parser], description=UDPATE_DESCRIPTION, help='update contact photos', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    edit = subparsers.add_parser('edit', parents=[file_parser, param_parser], description=EDIT_DESCRIPTION, help='edit contact links', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    delete = subparsers.add_parser('delete', parents=[file_parser, delete_parser, retry_parser], description=DELETE_DESCRIPTION, help='delete contact photos', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    return parser.parse_args()

def filename(filename):
    return os.path.splitext(filename)[0]

def score(score):
    score = int(score)
    if score < 0  or score > 100:
        raise argparse.ArgumentTypeError("Score must be between 0 and 100")
    return score


if __name__ == "__main__":
    main()
