# Sink

Sink is a utility that uses Facebook profile pictures to provide high resolution photos for your Google contacts. Sink links each of your Google contacts with their Facebook profile and stores those links to allow for quick updates.

## Installation

To install the required dependencies, run the following command.  This only needs to be done once.

    $ pip install -r requirements.txt

## Usage

When run for the first time, Sink will request permission to manage your contacts and ask for your Facebook username and password.  This is necessary to be able to access your accounts.  Sink will also create a database which contains these credentials and all created links created between Google contacts and Facebook friends.  This database is automatically updated anytime Sink is run.  **This data is not stored securely or protected in any way.  Secure your computer account to protect access to your database and do not share it others.**

### Basic Usage

To update your contact photos simply invoke the following command

    $ python sink.py update

### Commands

The following provides details on each of the Sink commands.  To view information about the possible commands invoke help

    $ python sink.py -h

#### Update

The update command updates your links and contact photos.  This command first creates links for all Google contacts that are not already stored in the database.  It attempts to automatically link contacts with Facebook friends by matching Google contact names with Facebook friend names.  You will then be prompted to manually link or ignore all contacts that could not be automatically linked.  Once all contacts have been linked your contact photos will be updated according to the created links.

The Sink update command is invoked by the following command

    $ python sink.py update [filename] [-a] [-i] [-s SCORE] [-m MATCHES] [-r RETRIES] [-d DELAY] [-e EXPIRY]

###### Optional Arguments

* `filename` - the name of shelf database file to use.  Defaults to `sinkshelf`.
* `-a, --auto-only` - skip all contacts not automatically linked.  This is useful when running Sink automatically so it does not prompt for user input.
* `-i, --update-ignored` - update all contacts previously ignored.  This is useful when you previously ignored a contact but recently became Facebook friends.
* `-s SCORE, --score SCORE` - score threshold to automatically link contacts.  Must be between 0 and 100.  The higher this number, the more similar contact and friends names must be to be automatically linked.  Defaults to 100 (perfect match).
* `-m MATCHES, --matches MATCHES` - the number of results to show when searching for friends to link to a contact.  Defaults to 5.
* `-r RETRIES, --retries RETRIES` - number of times to retry updating photos before failing.  Defaults to 3.
* `-d DELAY, --delay DELAY` - number of seconds to wait between contacts when updating photos.  Defaults to 0.
* `-e EXPIRY, --expiry EXPIRY` - number of days a photo is considered current and should not be updated.  Defaults to 30.

To view information about the Sink update command invoke help

    $ python sink.py update -h

#### Edit

The edit command allows you to edit your existing links.  You will be prompted to select a contact and then manually link or ignore that contact.

The Sink edit command is invoked by the following command

    $ python sink.py edit [filename] [-s SCORE] [-m MATCHES]

###### Optional Arguments

* `filename` - the name of shelf database file to use.  Defaults to `sinkshelf`.
* `-s SCORE, --score SCORE` - score threshold to automatically link contacts.  Must be between 0 and 100.  The higher this number, the more similar contact and friends names must be to be automatically linked.  Defaults to 100 (perfect match).
* `-m MATCHES, --matches MATCHES` - the number of results to show when searching for friends to link to a contact.  Defaults to 5.

To view information about the Sink edit command invoke help

    $ python sink.py edit -h

#### Delete

The delete command delete all Google contact photos provided by Sink.  Optionally, it will also delete all links saved in the database.

The Sink delete command is invoked by the following command

    $ python sink.py delete [filename] [-l] [-r RETRIES]

###### Optional Arguments

* `filename` - the name of shelf database file to use.  Defaults to `sinkshelf`.
* `-l, --delete-links` - delete saved links.
* `-r RETRIES, --retries RETRIES` - number of times to retry updating photos before failing.  Defaults to 3.

To view information about the Sink delete command invoke help

    $ python sink.py delete -h

## Implementation Details

#### Facebook

Sink scrapes your Facebook profile friends page to obtain a list of your friends' names and their Facebook usernames.  These usernames are then used to scrape your friends' profile pages to obtain their user ID.  This ID is then used to query the [Facebook Graph API](https://developers.facebook.com/docs/graph-api) (specifically [User Picture](https://developers.facebook.com/docs/graph-api/reference/user/picture)) to obtain their profile picture.

#### Google Contacts

Sink uses the [Google Contacts API](https://developers.google.com/google-apps/contacts) through the [Google Data Python Library](https://github.com/google/gdata-python-client).  Sink requests an OAuth token when run for the first time.  This token is then stored in the shelf database and used in future invocations.  Sink temporarily runs a minimal HTTP server listening on port 7465 when requesting an OAuth token in order to receive the response containing the token data.  The port listened on by the server can be changed in the source code.

#### Data Storage

Sink uses the [shelve](https://docs.python.org/library/shelve.html) module in the Python standard library to persist data between Sink invocations.  The created shelf database stores the following information:

* Facebook username
* Facebook password
* Google OAuth token
* Created links between Google contacts and Facebook friends

**This data is not stored securely or protected in any way.  Protect access to your shelf database and do not share it others.** This is because Sink needs to be able to read your Facebook username and password in order to scrape friend data.  Securing the shelf database would require user authentication on every invocation of Sink, which is inconvenient.  This is not a security concern because Sink is intended to be run locally so the shelf database file will be stored in a directory accessible only to the intended user.  To protect your shelf database take the appropriate steps to secure your computer user account.
