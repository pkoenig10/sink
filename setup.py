#!/usr/bin/env python

import pip

def install():
    pip.main(['install', 'beautifulsoup4', 'gdata', 'fuzzywuzzy'])

if __name__ == '__main__':
    install()
