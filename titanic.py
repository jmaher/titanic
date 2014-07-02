import os
import json
import httplib
import re
import urllib
import argparse
import sys
import datetime

branchPaths = {
    'mozilla-central' : 'mozilla-central',
    'mozilla-inbound' : 'integration/mozilla-inbound',
    'b2g-inbound'     : 'integration/b2g-inbound',
    'fx-team'         : 'integration/fx-team'
}

platforms = ['linux32', 'linux64', 'osx10.6', 'osx10.7', 'osx10.8', 'winxp','win7','win764','win8']

platformXRef = {
    'Linux'                            : 'linux32',
    'Ubuntu HW 12.04'                  : 'linux32',
    'Ubuntu VM 12.04'                  : 'linux32',
    'Rev3 Fedora 12'                   : 'linux32',
    'Linux x86-64'                     : 'linux64',
    'Rev3 Fedora 12x64'                : 'linux64',
    'Ubuntu VM 12.04 x64'              : 'linux64',
    'Ubuntu HW 12.04 x64'              : 'linux64',
    'Ubuntu ASAN VM 12.04 x64'         : 'linux64',
    'Rev4 MacOSX Snow Leopard 10.6'    : 'osx10.6',
    'Rev4 MacOSX Lion 10.7'            : 'osx10.7',
    'OS X 10.7'                        : 'osx10.7',
    'Rev5 MacOSX Mountain Lion 10.8'   : 'osx10.8',
    'WINNT 5.2'                        : 'winxp',
    'Windows XP 32-bit'                : 'winxp',
    'Windows 7 32-bit'                 : 'win7',
    'Windows 7 64-bit'                 : 'win764',
    'WINNT 6.1 x86-64'                 : 'win764',
    'WINNT 6.2'                        : 'win8',
    'Android Armv6'                    : 'android-armv6',
    'Android 2.2 Armv6'                : 'android-armv6',
    'Android Armv6 Tegra 250'          : 'android-armv6',
    'Android X86'                      : 'android-x86',
    'Android 2.2'                      : 'android2.2',
    'Android 2.2 Tegra'                : 'android2.2',
    'Android 2.3 Emulator'             : 'android2.3',
    'Android no-ionmonkey'             : 'android-no-ion',
    'Android 4.0 Panda'                : 'android4.0',
    'b2g_emulator_vm'                  : 'b2g-vm',
    'b2g_ubuntu64_vm'                  : 'b2g-vm',
    'b2g_ubuntu32_vm'                  : 'b2g-vm',
    'b2g_ics_armv7a_gecko_emulator_vm' : 'b2g-vm',
    'b2g_ics_armv7a_gecko_emulator'    : 'b2g-emulator'
}

#
# The following platforms were not considered
# We might want to add them in the future
#
'''
b2g_mozilla-central_macosx64_gecko build opt
b2g_mozilla-central_macosx64_gecko-debug build opt
b2g_macosx64 opt gaia-ui-test

linux64-br-haz_mozilla-central_dep opt

Android 4.2 x86 build
Android 4.2 x86 Emulator opt androidx86-set-4

b2g_mozilla-central_win32_gecko-debug build opt
b2g_mozilla-central_win32_gecko build opt
b2g_mozilla-central_linux32_gecko build opt
b2g_mozilla-central_linux32_gecko-debug build opt

b2g_mozilla-central_emulator-kk_periodic opt
b2g_mozilla-central_emulator-kk-debug_periodic opt
b2g_mozilla-central_emulator-kk_nonunified opt
b2g_mozilla-central_emulator-kk-debug_nonunified opt

b2g_mozilla-central_emulator-jb-debug_dep opt
b2g_mozilla-central_emulator_dep opt
b2g_mozilla-central_emulator-debug_dep opt
b2g_mozilla-central_emulator-jb_dep opt
b2g_mozilla-central_emulator_nonunified opt
b2g_mozilla-central_emulator-debug_nonunified opt
b2g_mozilla-central_emulator-jb-debug_nonunified opt
b2g_mozilla-central_emulator-jb_nonunified opt

b2g_mozilla-central_nexus-4_periodic opt
b2g_mozilla-central_nexus-4_eng_periodic opt

b2g_mozilla-central_linux64_gecko build opt
b2g_mozilla-central_linux64_gecko-debug build opt

b2g_mozilla-central_hamachi_eng_dep opt
b2g_mozilla-central_hamachi_periodic opt

b2g_mozilla-central_flame_eng_dep opt
b2g_mozilla-central_flame_periodic opt

b2g_mozilla-central_helix_periodic opt

b2g_mozilla-central_wasabi_periodic opt
'''


def getPushLog(branch, startDate):
    # Example
    # Get PushLog for 2014-06-16
    # https://hg.mozilla.org/integration/mozilla-inbound/json-pushes?startdate=2014-06-18

    conn = httplib.HTTPSConnection('hg.mozilla.org')
    pushLogURL = "/%s/json-pushes?startdate=%s" % (branchPaths[branch], startDate)
    conn.request("GET", pushLogURL)
    pushLogResponse = conn.getresponse()

    pushAll = []

    pushLogJSON = pushLogResponse.read()
    pushLogResponse.close()
    pushLog = json.loads(pushLogJSON)

    # pushLog has a ID associated with each push. Each push also has a
    # date associated with it. For now we ignore the dates while considering the pushLogs.
    # Every push also has a set of revision numbers associated with it. We are interested
    # in the last of the revision numbers and only the first 12 characters.
    for entry in pushLog:
        pushAll.append(pushLog[entry]['changesets'][-1][:12])

    return pushAll


def parseBuildInfo(buildInfo, branch):
    buildInfoList = buildInfo.split(" " + branch + " ")
    platform = buildInfoList[0]
    buildType = branch.join(buildInfoList[1:])

    types = buildType.split('test')
    buildType, testType = types[0].strip(), 'test'.join(types[1:]).strip()
    buildType = buildType.strip()

    # Note: Talos isn't explicitly handled here. We might want to clean this up to handle
    # talos tests and builds explicitly.

    if buildType not in ['opt', 'debug', 'build'] and not testType:
        testType = buildType
        buildType = 'opt'

    for p in platformXRef:
        if re.match(p, platform.strip()):
            return platformXRef[p], buildType, testType
            #return platformXRef[p], buildType, testType
    return '','',''


def getMatch(string, refList):

    # If the list is empty default to 'all' and return True.
    if (refList == []):
        return True

    if string == '':
        return False

    for item in refList:
    # We need exact matches for test bisection. However, if we'd like to have more flexibility we
    # could potentially use regular expresssions to look for matches.
    #    if re.match(string.lower(), item.lower()) or re.match(item.lower(), string.lower()):
    #        return True
        if string == item:
           return True
    return False


def downloadCSetResults(branch, rev):
    # Example
    # Get Results for CSet Revision: 3b75b48cbaca
    # https://tbpl.mozilla.org/php/getRevisionBuilds.php?branch=mozilla-inbound&rev=3b75b48cbaca

    conn = httplib.HTTPSConnection('tbpl.mozilla.org')
    csetURL = "/php/getRevisionBuilds.php?branch=%s&rev=%s&showall=1" % (branch, rev)
    conn.request("GET", csetURL)
    csetResponse = conn.getresponse()

    csetData = csetResponse.read()
    csetResponse.close()

    try:
        ret = json.loads(csetData)
    except:
        print "Error loading results in JSON Format"
        ret = {}
    return ret


def getCSetResults(branch, getPlatforms, getTests, rev):
    csetResults = []

    resultData = downloadCSetResults(branch, rev)

    # TODO: Check for build corener cases

    for entry in resultData:
        notes = ''
        if 'result' not in entry:
            continue

        result = entry['result']
        platform, buildType, testType = parseBuildInfo(entry['buildername'], branch)

        if not platform:
            continue
        if entry['notes']:
            notes = entry['notes'][0]['note'].replace("'", '')

        if getMatch(testType, getTests) and getMatch(platform, getPlatforms):
            csetResults.append([result, platform, buildType, testType, entry['buildername'], notes])
    return csetResults


def runTitanicNormal(args, allPushes):
    for push in allPushes:
        print 'Getting Results for %s' % (push)
        results = getCSetResults(args.branch, args.platform, args.tests, push)
        # Mostly hooks would go in here. For now print all the results
        for i in results:
            print i

def runTitanicAnalysis(args, allPushes):
    if args.revision not in allPushes:
        print 'Revision not found in the current range. Consider increasing range!'
        sys.exit(1)

    revPos = allPushes.index(args.revision)
    print "Revision " + args.revision + " at position " + str(revPos)
    for push in allPushes[revPos+1:]:
        pushResults = getCSetResults(args.branch, args.platform, args.tests, push)
        print pushResults
        if (len(pushResults) > 0) and (pushResults[0][0] == 'success') and (pushResults[0][2] != ''):
            revLastPos = allPushes.index(push)
            return allPushes[revPos+1:revLastPos+1], pushResults[0][4]
    print 'Revision that successfully passed ' + str(args.tests) + ' not found in the current range. Consider increasing range!'
    sys.exit(1)


def printCommands(revList, buildername, args):
    for rev in revList:
        print 'python trigger.py --buildername ' + str(buildername) + '--branch ' + str(args.branch) + ' --rev ' + str(rev)


def runTitanic(args):
    # Default to a range of 1 day
    startDate = datetime.datetime.utcnow() - datetime.timedelta(hours=(args.delta*24))
    print startDate.strftime('%Y-%m-%d')

    allPushes = getPushLog(args.branch, startDate.strftime('%Y-%m-%d'))
    print allPushes

    if args.revision:
        # We might want to consider having an explicit flag for Analysis Mode
        revList, buildername = runTitanicAnalysis(args, allPushes)
        printCommands(revList, buildername, args)
    else:
        runTitanicNormal(args, allPushes)


def verifyArgs(args):
    if args.branch not in branchPaths:
        print 'error: unknown branch: %s' % (args.branch)
        sys.exit(1)

    flag = True;
    for p in args.platform:
        flag = flag and getMatch(p, platforms)
        if flag == False:
            print 'error: unknown platform: %s' % (p)
            sys.exit(1)

    if args.revision:
        if args.tests == [] or (len(args.tests) != 1):
            print 'For bisection in the cloud you need to specify test you are interested in!'
            sys.exit(1)
        elif args.platform == [] or (len(args.platform) != 1):
            print 'To enable bisection in cloud you need to specify platform you are interested in!'
            sys.exit(1)


def setupArgsParser():
    parser = argparse.ArgumentParser(description='Run Titanic')
    parser.add_argument('-b', action='store', dest='branch', default='mozilla-central',
                        help='Branch for which to retrieve results.')
    parser.add_argument('-t', action='append', dest='tests', default=[],
                        help='Tests for which to retreive results. You can specify more than one.')
    parser.add_argument('-p', action='append', dest='platform', default=[],
                        help='Platforms for which to retrieve results. You can specify more than one.')
    parser.add_argument('-d', action='store', dest='delta', default=1, type=int,
                        help='Range for which to retrieve results. Range in days.')
    parser.add_argument('-r', action='store', dest='revision', default=0,
                        help='Revision for which to start bisection with!')
    return parser.parse_args()


if __name__ == '__main__':
    args = setupArgsParser()
    verifyArgs(args)
    runTitanic(args)