#!/usr/bin/env python3
import argparse
from sys import argv, exit as sysexit, platform
import os
from os.path import expanduser, join as pathjoin, isdir, splitext
from os.path import basename, dirname, abspath
import log
import webutil
import bingwallpaper
import record
import setter
import sched
import time

NAME = 'pybingwallpaper'
REV  = '1.2.0'
LINK = 'https://github.com/genzj/pybingwallpaper'
HISTORY_FILE = pathjoin(expanduser('~'), 'bing-wallpaper-history.json')

_logger = log.getChild('main')

def load_setters():
    if platform == 'win32':
        return ['no', 'win']
    else:
        return ['no', 'gnome3', 'gnome2']

def parseargs(args):
    setters = load_setters()
    parser = argparse.ArgumentParser(prog=NAME,
            description='Download the wallpaper offered by Bing.com '
            +'and set it current wallpaper background.')
    parser.add_argument('-v', '--version', action='version',
            version='%(prog)s-{} ({})'.format(REV, LINK),
            help='show version information')
    parser.add_argument('-b', '--background', default=False,
            action='store_true',
            help='''work in background (daemon mode) and check
            wallpaper periodically (interval can be set by --interval).''')
    parser.add_argument('-c', '--country', default=None,
            choices=('au', 'ca', 'cn', 'de', 'fr', 'jp', 'nz', 'us', 'uk'), 
            help='''select country code sent to bing.com.
            bing.com in different countries may show different
            backgrounds.''')
    parser.add_argument('-d', '--debug', default=0,
            action='count',
            help='''enable debug outputs. 
            The more --debug the more detailed the log will be''')
    parser.add_argument('-f', '--force', default=False,
            action='store_true',
            help='''adopt this photo even if its size may
                    be strange to be wallpaper. Disabled by
                    default''')
    parser.add_argument('--interval', type=int, default=8,
            help='''interval between each two wallpaper checkings 
                    in unit of hours. applicable only in `background` mode''')
    parser.add_argument('-k', '--keep-file-name', default=False,
            action='store_true',
            help='''keep the original filename. By default
            downloaded file will be renamed as 'wallpaper.jpg'.
            Keep file name will retain all downloaded photos
            ''')
    parser.add_argument('-o','--offset', type=int, default='0',
            help='''start downloading from the photo of 'N' days ago.
                    specify 0 to download photo of today.''')
    parser.add_argument('--persistence', type=int, default='3',
            help='''go back for at most N-1 pages if photo of today isn\'t for
            wallpaper. Backward browsing will be interrupted before N-1 pages
            tried if either a downloaded page found or a wallpaper link read''')
    parser.add_argument('--redownload', default=False,
            action='store_true',
            help='''do not check history records. Download
                    must be done. **This download will still
                    be recorded in history file.**
            ''')
    parser.add_argument('-s', '--setter', choices=setters,
            default=setters[1],
            help='''specify interface to be called for
                    setting wallpaper. 'no'
                    indicates downloading-only; 'gnome2/3'
                    are only for Linux with gnome; 'win' is
                    for Windows only. Customized setter can
                    be added as dev doc described. Default: {}
            '''.format(setters[1]))
    parser.add_argument('--setter-args', default=[], action='append',
            help='''go back for at most N-1 pages if photo of today isn\'t for
            ''')
    parser.add_argument('-t', '--output-folder',
            default=pathjoin(expanduser('~'), 'MyBingWallpapers'),
            help='''specify the folder to store photos.
                    Use '~/MyBingWallpapers' folder in Linux or
                    'My Documents/MyBingWallpapers' in Windows by default
                ''')
    config = parser.parse_args(args)
    config.setter_args = ','.join(config.setter_args).split(',')
    return config

def prepare_output_dir(d):
    os.makedirs(d, exist_ok=True)
    if isdir(d):
        return True
    else:
        _logger.critical('can not create output folder %s', d)

def download_wallpaper(config):
    idx = config.offset
    p = config.persistence
    s = bingwallpaper.BingWallpaperPage(idx, p, filter_wp = not config.force, country_code = config.country)

    _logger.debug(repr(s))
    s.load()
    _logger.debug(str(s))
    if not s.loaded():
        _logger.fatal('can not load url %s. aborting...', s.url)
        return None
    for i in s.images():
        wplink = i['url']

        if wplink:
            outfile = get_output_filename(config, wplink)
            rec = record.default_manager.get(wplink, None)

            if rec and outfile == rec['local_file']:
                if not config.redownload:
                    _logger.info('file has been downloaded before, exit')
                    return None
                else:
                    _logger.info('file has been downloaded before, redownload it')

            _logger.info('download photo of "%s"', i['copyright'])
            picture_content = webutil.loadurl(wplink)
            if picture_content:
                with open(outfile, 'wb') as of:
                    of.write(picture_content)
                    _logger.info('file saved %s', outfile)
                r = record.DownloadRecord(wplink, outfile)
                return r
        _logger.debug('no wallpaper, try next')
        
    if s.filtered > 0:
        _logger.info('%d picture(s) filtered, try again with -f option if you want them',
                     s.filtered)
    _logger.info('bad luck, no wallpaper today:(')
    return None

def get_output_filename(config, link):
    filename = basename(link)
    if not config.keep_file_name:
        filename = 'wallpaper{}'.format(splitext(filename)[1])
    return pathjoin(config.output_folder, filename)

def load_history():
    try:
        f = open(HISTORY_FILE, 'r')
    except FileNotFoundError:
        _logger.info('{} not found, ignore download history'.format(HISTORY_FILE))        
    except Exception:
        _logger.warning('error occurs when recover downloading history', exc_info=1)
    else:
        record.default_manager.load(f)
        f.close()

def save_history(r, keepold=False):
    if not keepold:
        record.default_manager.clear()
    record.default_manager.add(r)
    try:
        f = open(HISTORY_FILE, 'w')
        f.truncate(0)
    except Exception:
        _logger.warning('error occurs when store downloading history',
                        exc_info=1)
    else:
        record.default_manager.save(f)
        f.close()

def set_debug_details(level):
    if not level:
        l = log.INFO
    elif level == 1:
        l = log.DEBUG
    elif level >= 2:
        l = log.PAGEDUMP
    log.setDebugLevel(l)

def main(config, daemon=None):
    if daemon: _logger.info('daemon %s triggers an update', str(daemon))
    setter.load_ext_setters(dirname(abspath(argv[0])))

    prepare_output_dir(config.output_folder)

    load_history()
    filerecord = download_wallpaper(config)

    if filerecord:
        save_history(filerecord)
    if not filerecord or config.setter == 'no':
        _logger.info('nothing to set')
    else:
        s = setter.get(config.setter)()
        _logger.info('setting wallpaper %s', filerecord['local_file'])
        s.set(filerecord['local_file'], config.setter_args)
        _logger.info('all done. enjoy your new wallpaper')

    if daemon: schedule_next_poll(config, daemon)

def schedule_next_poll(config, daemon):
    if config.background and daemon:
        _logger.debug('schedule next running in %d seconds', config.interval*3600)
        daemon.enter(config.interval*3600, 1, main, (config, daemon))
    elif not config.background:
        _logger.error('not in daemon mode')
    elif not daemon:
        _logger.error('no scheduler')

def start_daemon(config):
    daemon = sched.scheduler()
    
    main(config, daemon)
    _logger.info('daemon %s is running', str(daemon))
    daemon.run()
    _logger.info('daemon %s exited', str(daemon))

if __name__ == '__main__':
    config = parseargs(argv[1:])
    set_debug_details(config.debug)
    _logger.debug(config)
    if config.background:
        start_daemon(config)
    else:
        main(config, None)
    sysexit(0)
