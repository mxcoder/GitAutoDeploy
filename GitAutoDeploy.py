#!/usr/bin/env python

import json, urlparse, sys, os, cgi
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from subprocess import call

class GitAutoDeploy(BaseHTTPRequestHandler):

    CONFIG_FILEPATH = './GitAutoDeploy.conf.json'
    config = None
    quiet = False
    daemon = False

    @classmethod
    def getConfig(myClass):
        if(myClass.config == None):
            try:
                configString = open(myClass.CONFIG_FILEPATH).read()
            except:
                sys.exit('Could not load ' + myClass.CONFIG_FILEPATH + ' file')

            try:
                myClass.config = json.loads(configString)
            except:
                sys.exit(myClass.CONFIG_FILEPATH + ' file is not valid json')

            for repository in myClass.config['repositories']:
                if(not os.path.isdir(repository['path'])):
                    sys.exit('Directory ' + repository['path'] + ' not found')
                if(not os.path.isdir(repository['path'] + '/.git')):
                    sys.exit('Directory ' + repository['path'] + ' is not a Git repository')

        return myClass.config

    def do_POST(self):
        urls = self.parseRequest()
        for url in urls:
            paths = self.getMatchingPaths(url[0], url[1])
            for path in paths:
                self.pull(path)
                self.deploy(path)

    def parseRequest(self):
        items = []
        item = None
        length = int(self.headers.getheader('content-length'))
        contenttype = self.headers.getheader('content-type')
        githubheader = self.headers.getheader('X-Github-Event')
        content = self.rfile.read(length)
        if not self.quiet:
          print self.headers, contenttype, content
        # Needed for bitbucket push hook
        if (contenttype == "application/x-www-form-urlencoded"):
          postvars = cgi.parse_qs(content, keep_blank_values=1)
          if postvars['payload']:
            item = json.loads(postvars['payload'][0].strip())
            item['bitbucket-push'] = True
        # Most common operation, bitbucket and github uses this
        if (contenttype == "application/json"):
          item = json.loads(content)
        if item:
            if not self.quiet:
              print item
            # Github
            if not githubheader is None:
              # push
              if githubheader == "push":
                items.append(( item['repository']['full_name'], item['ref'].replace('refs/heads/',"") ))
                if not self.quiet:
                  print "GitHub Push received", items
              # pr-merged
              if (githubheader == "pull_request" and item['action'] == "closed" and item['pull_request']['merged']):
                items.append(( item['repository']['full_name'], item['pull_request']['base']['ref'] ))
                if not self.quiet:
                  print "GitHub PR-merged received", items
            # Bitbucket Push
            elif 'bitbucket-push' in item:
              items.append(( item['repository']['absolute_url'].strip('/'), item['commits'][-1]['branch'] ))
              if not self.quiet:
                print "BitBucket push received", items
            # Bitbucket PR-merged
            elif 'pullrequest_merged' in item:
              items.append(( item['pullrequest_merged']['destination']['repository']['full_name'], item['pullrequest_merged']['destination']['branch']['name'] ))
              if not self.quiet:
                print "BitBucket pr-merged received", items
        return items

    def getMatchingPaths(self, repoUrl, repoBranch):
        res = []
        config = self.getConfig()
        for repository in config['repositories']:
            if(repository['url'] == repoUrl and repository['branch'] == repoBranch):
                res.append(repository['path'])
        return res

    def respond(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

    def pull(self, path):
        if(not self.quiet):
            print "\nPost push request received"
            print 'Updating ' + path
        call(['cd "' + path + '" && git pull'], shell=True)

    def deploy(self, path):
        config = self.getConfig()
        for repository in config['repositories']:
            if(repository['path'] == path):
                if 'deploy' in repository:
                     if(not self.quiet):
                         print 'Executing deploy command'
                     call(['cd "' + path + '" && ' + repository['deploy']], shell=True)
                break

def main():
    try:
        server = None
        for arg in sys.argv:
            if(arg == '-d' or arg == '--daemon-mode'):
                GitAutoDeploy.daemon = True
                GitAutoDeploy.quiet = True
            if(arg == '-q' or arg == '--quiet'):
                GitAutoDeploy.quiet = True

        if(GitAutoDeploy.daemon):
            pid = os.fork()
            if(pid != 0):
                sys.exit()
            os.setsid()

        if(not GitAutoDeploy.quiet):
            print 'GitAutoDeploy Service v 0.1 started'
        else:
            print 'GitAutoDeploy Service v 0.1 started in daemon mode'

        server = HTTPServer(('', GitAutoDeploy.getConfig()['port']), GitAutoDeploy)
        server.serve_forever()
    except (KeyboardInterrupt, SystemExit) as e:
        if(e): # wtf, why is this creating a new line?
            print >> sys.stderr, e

        if(not server is None):
            server.socket.close()

        if(not GitAutoDeploy.quiet):
            print 'Goodbye'

if __name__ == '__main__':
     main()
