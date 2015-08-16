#!/usr/bin/env python

import pip

def install():
    pip.main(['install', 'beautifulsoup4'])
    pip.main(['install', 'gdata'])
    pip.main(['install', 'fuzzywuzzy'])

if __name__ == '__main__':
    install()