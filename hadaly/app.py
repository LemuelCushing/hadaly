# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals, absolute_import
import shutil

from kivy import require

require('1.9.1')

import os, json
from sys import argv

from .meta import version as app_version
from urllib.parse import urlencode
import re

from urllib.parse import urlparse
from urllib.parse import quote

from lxml import html
import tempfile

from PIL import Image
import tarfile


from kivy.config import Config
Config.set('graphics', 'fullscreen', 'auto')

from kivy.app import App
from kivy.core.window import Window
from kivy.properties import StringProperty, ListProperty, DictProperty
from kivy.uix.screenmanager import ScreenManager, FadeTransition
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.factory import Factory
from kivy.uix.progressbar import ProgressBar
from .editor import Slide, SlideInfoDialog, DraggableSlide
from .viewer import SlideBox
from kivy.logger import Logger
from kivy.network.urlrequest import UrlRequest
from .search import ItemButton
from kivy.uix.filechooser import FileChooserListView


class HadalyApp(App):
    presentation = DictProperty({'app': ('hadaly', app_version), 'title': '', 'slides': []})

    slides_list = ListProperty()

    filename = StringProperty('')

    dirname = StringProperty('')

    use_kivy_settings = True

    def build(self):
        self.icon = str('data/icon.png')
        self.title = str('Hadaly')

        root = Manager(transition=FadeTransition(duration=.35))

        self.searchscreen = Factory.SearchScreen(name='search')
        self.viewerscreen = Factory.ViewerScreen(name='viewer')
        self.editorscreen = Factory.EditorScreen(name='editor')

        root.add_widget(self.editorscreen)
        root.add_widget(self.viewerscreen)
        root.add_widget(self.searchscreen)

        return root

    def build_config(self, config):
        config.add_section('general')
        config.add_section('viewer')
        config.add_section('editor')
        config.add_section('search')
        config.set('general', 'switch_on_start', '0')
        config.set('editor', 'autosave_time', '15')
        config.set('editor', 'autosave', '0')
        config.set('editor', 'font_size', '12')
        config.set('editor', 'last_dir', os.path.expanduser('~'))
        config.set('editor', 'cols', '6')
        config.set('viewer', 'thumb', '1')
        config.set('viewer', 'thumb_pos', 'bottom left')
        config.set('viewer', 'font_size', '15')
        config.set('viewer', 'caption_pos', 'bottom')
        config.set('search', 'search_rpp', '10')

    def build_settings(self, settings):
        settings.add_json_panel('Hadaly',
                                self.config,
                                'hadaly/data/settings_panel.json')

    def on_start(self):
        self.tempdir = tempfile.mkdtemp()
        self.presentation['title'] = _('New Title')
        try:
            if argv[1].endswith('.opah'):
                self.load_slides(os.path.dirname(argv[1]), [os.path.basename(argv[1])])
                Logger.info('Application: file \'{file}\' loaded'.format(file=self.filename))
                if self.config.getint('general', 'switch_on_start') == 1:
                    self.root.current = 'viewer'
        except IndexError:
            pass

    def load_slides(self, path, filename):

        try:
            with tarfile.open(os.path.join(path, filename[0]), 'r:*') as tar:
                tar.extractall(path=self.tempdir)
        except ValueError as msg:
            Logger.debug('Application: {msg}'.format(msg=msg))
            self.show_popup(_('Error'), _('File is not valid.'))
        except IndexError as msg:
            Logger.debug('Application: {msg}'.format(msg=msg))
            self.show_popup(_('Error'), _('No file selected'))
        else:
            if len(self.root.current_screen.slides_view.grid_layout.children) > 0:
                self.create_presentation()

            try:
                with open(os.path.join(self.tempdir, 'presentation.json'), 'r') as fd:
                    data = json.load(fd)
            except ValueError as msg:
                Logger.debug('Application (JSON Loading): {msg}'.format(msg=msg))

            self.dirname = path
            self.filename = filename[0]

            self.presentation = data
            self.presentation_title = data['title']

            for slide in reversed(self.presentation['slides']):
                # TODO: Remove tmp in filename on save
                thumb_src = os.path.join(self.tempdir, slide['thumb_src'])
                img_src = os.path.join(self.tempdir, slide['img_src'])
                index = self.presentation['slides'].index(slide)
                self.presentation['slides'][index]['thumb_src'] = thumb_src
                self.presentation['slides'][index]['img_src'] = img_src

                img_slide = Factory.Slide(img_src=img_src,
                                          thumb_src=thumb_src,
                                          artist=slide['artist'],
                                          title=slide['title'],
                                          year=slide['year']
                                          )

                drag_slide = Factory.DraggableSlide(img=img_slide, app=self)

                self.root.current_screen.slides_view.grid_layout.add_widget(drag_slide)

    def create_presentation(self):
        '''Remove all slides, clear presentation and initialise a new one.
        '''
        self.root.current_screen.slides_view.grid_layout.clear_widgets()
        self.root.get_screen('viewer').carousel.clear_widgets()
        self.presentation = {'app': ('hadaly', app_version), 'title': _('New Title'), 'slides': []}
        self.filename = self.dirname = ''

    def update_presentation(self, type, old_index, new_index):
        """
        :param type: type of update to do : 'mv' (move) or 'rm' (remove) or 'update'
        :param old_index: previous index of item in grid layout as an integer.
        :param new_index: new index of item in grid layout as an integer.
        """
        if type == 'rm':
            Logger.debug('Application: Removing presentation item.')
            self.presentation['slides'].pop(old_index)
            try:
                self.root.get_screen('viewer').update_carousel()
            except AttributeError:
                Logger.debug('Application: Viewer dialog not yet added !')
        elif type == 'mv':
            Logger.debug('Application: Moving presentation item.')
            try:
                Logger.debug('Application: Moved {slide} at position (in grid layout) {index} to {new_index}'.format(
                    slide=self.presentation['slides'][old_index],
                    index=old_index, new_index=new_index))

                item = self.presentation['slides'].pop(old_index)
                self.presentation['slides'].insert(new_index, item)
                try:
                    self.root.get_screen('viewer').update_carousel()
                except AttributeError:
                    Logger.debug('Application: Viewer dialog not yet added !')
            except TypeError:
                Logger.exception('Application: Only one slide in presentation view. (BUG)')
        elif type == 'update':
            Logger.debug('Application: Updating presentation.')
            self.presentation['slides'][old_index] = self.root.get_screen('editor').slides_view.grid_layout.children[
                old_index].img.get_slide_info()

    def show_open(self):
        popup = Factory.OpenDialog()
        popup.open()

    def show_file_explorer(self):
        popup = Popup(size_hint=(0.8, 0.8))
        file_explorer = FileChooserListView(filters=['*.jpg', '*.png', '*.jpeg'])
        if os.path.exists(self.config.get('editor', 'last_dir')):
            file_explorer.path = self.config.get('editor', 'last_dir')
        file_explorer.bind(on_submit=self.show_add_slide)
        file_explorer.popup = popup
        popup.content = file_explorer
        popup.title = _('File explorer')
        popup.open()

    def show_save(self, action):
        """Show save dialog.

        If action == 'save', dialog is not shown and file is
        saved based on self.dirname and self.filename.
        """
        if len(self.presentation['slides']) == 0:
            self.show_popup(_('Error'), _('Nothing to save...'))
        else:
            if self.filename and action == 'save':
                self.save(self.dirname, self.filename)
            else:
                popup = Factory.SaveDialog()
                popup.open()

    def save(self, path, filename):
        """Save presentation as *.opah file.

        :param path: path where to save to as string
        :param filename: filename of file to save as string
        """
        if not filename.endswith('.opah'):
            filename = '.'.join((filename, 'opah'))

        self.filename = filename
        self.dirname = path

        tar = tarfile.open(os.path.join(path, filename), 'a')

        # Add image file to *.opah file
        try:
            for file in [slide for slide in self.presentation['slides']]:
                if os.path.exists(file['img_src']):
                    tar.add(os.path.relpath(file['img_src']),
                            arcname=os.path.basename(file['img_src']))
                else:
                    tar.add(os.path.relpath(os.path.join(self.tempdir, file['img_src'])),
                            arcname=os.path.basename(file['img_src']))
                if os.path.exists(file['thumb_src']):
                    tar.add(os.path.relpath(os.path.join(self.tempdir, file['thumb_src'])),
                            arcname=os.path.basename(file['thumb_src']))
                else:
                    tar.add(os.path.relpath(file['thumb_src']),
                            arcname=os.path.basename(file['thumb_src']))
        except IndexError:
            Logger.exception('Saving:')
        except IOError:
            Logger.exception('Saving:')

        # Create json file with slides metadata
        for slide in self.presentation['slides']:
            Logger.debug('Save: thumb {thumb} from img {img}'.format(thumb=slide['thumb_src'],
                                                                     img=slide['img_src']))
            slide['img_src'] = os.path.basename(slide['img_src'])
            slide['thumb_src'] = os.path.basename(slide['thumb_src'])

        try:
            with open(os.path.join(self.tempdir, 'presentation.json'), 'w') as fd:
                json.dump(self.presentation, fd)
        except IOError as msg:
            Logger.debug('Application: {msg}'.format(msg=msg[1]))
            self.show_popup('Error', msg[1])

        # Add json file to *.opah file
        tar.add(os.path.join(self.tempdir, 'presentation.json'), 'presentation.json')
        tar.close()

    def switch_slide(self, index):
        """Switch index of carousel to current index.

        :param index:
        """
        self.root.current_screen.carousel.index = index

    def add_slide_to_compare(self, index):
        slide = SlideBox(slide=self.presentation['slides'][index])
        self.root.current_screen.box.add_widget(slide, 0)
        # Change scatter position to compensate screen split.
        pos = self.root.current_screen.carousel.current_slide.viewer.pos
        self.root.current_screen.carousel.current_slide.viewer.pos = (pos[0] / 2, pos[1])

    def rm_slide_to_compare(self):
        self.root.current_screen.box.remove_widget(self.root.current_screen.box.children[0])
        pos = self.root.current_screen.carousel.current_slide.viewer.pos
        self.root.current_screen.carousel.current_slide.viewer.pos = (pos[0] * 2, pos[1])

    def compare_slide(self, index=None, action='add'):
        """Add new SlideBox to ViewerScreen based on SlideButton index.

        :param index: index of slide as int.
        :param action: 'add' or 'rm'
        """
        if action == 'add':
            slide = SlideBox(slide=self.presentation['slides'][index])
            self.root.current_screen.box.add_widget(slide, 0)
            # Change scatter position to compensate screen split.
            pos = self.root.current_screen.carousel.current_slide.viewer.pos
            self.root.current_screen.carousel.current_slide.viewer.pos = (pos[0] / 2, pos[1])
        elif action == 'rm':
            self.root.current_screen.box.remove_widget(self.root.current_screen.box.children[0])
            pos = self.root.current_screen.carousel.current_slide.viewer.pos
            self.root.current_screen.carousel.current_slide.viewer.pos = (pos[0] * 2, pos[1])

    def set_presentation_title(self):
        popup = Factory.TitleDialog()
        popup.open()

    def show_add_slide(self, original_src, *args):
        """Show dialog to add a slide.
        """
        original_src.popup.dismiss()
        self.config.set('editor', 'last_dir', os.path.dirname(original_src.selection[0]))
        thumb_src = self.create_thumbnail(original_src.selection[0])
        slide_popup = SlideInfoDialog(slide=Slide(img_src=original_src.selection[0],
                                                  thumb_src=thumb_src,
                                                  artist='',
                                                  title='',
                                                  year=''))
        slide_popup.open()

    def add_slide(self, slide):
        """Add slide to presentation.

        :param slide: slide as object
        """
        # Logger.debug('Application: Adding to presentation {slide}'.format(slide=slide.get_slide_info()))
        img_slide = DraggableSlide(img=slide, app=self)
        self.presentation['slides'].insert(0, slide.get_slide_info())
        self.root.get_screen('editor').slides_view.grid_layout.add_widget(img_slide)

    def create_thumbnail(self, img_src):
        Logger.debug('Creating thumbnail from {src}'.format(src=img_src))
        image = Image.open(img_src)
        if Image.VERSION == '1.1.7':
            image.thumbnail((200, 200))
        else:
            image.thumbnail((200, 200), Image.ANTIALIAS)
        thumb_filename = ''.join(('thumb_', os.path.basename(img_src)))
        thumb_src = os.path.join(self.tempdir, thumb_filename)
        image.save(thumb_src)
        Logger.debug('Application: Thumbnail created at {thumb}'.format(thumb=thumb_src))
        return thumb_src

    def show_popup(self, type, msg):
        """
        :param type: popup title as string.
        :param msg: content of the popup as string.
        """
        popup = Popup(title=type, size_hint=(0.5, 0.2))
        popup.content = Label(text=msg, id='label')
        popup.open()

    def switch_to_viewer(self):
        if not self.presentation['slides']:
            self.show_popup(_('Error'), _('Presentation is empty...\n Please add a slide first.'))
        else:
            self.root.current = 'viewer'

    def search_flickr(self, term):
        """make a search request on flickr and return results

        :param term: the term to search.
        :return results: response in json
        """
        api_key = '624d3a7086d14e85f1422430f0b889a1'
        base_url = 'https://api.flickr.com/services/rest/?'
        method = 'flickr.photos.search'
        params = urlencode([('method', method),
                                   ('text', term),
                                   ('api_key', api_key),
                                   ('format', 'json'),
                                   ('nojsoncallback', 1),
                                   ('per_page', 20),
                                   ('content_type', 4)
                                   ])
        url = ''.join((base_url, params))
        result = self.request(url)
        return result

    def request(self, url):
        url = quote(url, safe="%/:=&?~#+!$,;'@()*[]")
        req = UrlRequest(url, debug=True)
        req.wait()
        return req.result

    def download_img(self, url, slide, wait=False):
        pb = ProgressBar(id='_pb')
        self.progress_dialog = Popup(title=_('Downloading...'),
                                     size_hint=(0.5, 0.2), content=pb, auto_dismiss=False)
        url = quote(url, safe="%/:=&?~#+!$,;'@()*[]")
        path = os.path.join(self.tempdir,
                            os.path.basename(urlparse(url).path))
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 5.1; rv:31.0) Gecko/20100101 Firefox/31.0"}
        req = UrlRequest(url, self.reload_slide, file_path=path, on_progress=self.show_download_progress,
                         req_headers=headers, debug=True)
        self.progress_dialog.open()

    def show_download_progress(self, req, down_size, end_size):
        self.progress_dialog.content.max = end_size
        self.progress_dialog.content.value = down_size
        if down_size == end_size:
            self.progress_dialog.dismiss()

    def reload_slide(self, request, data):
        Logger.debug('Application: Download finished, reloading slide source.')
        slide_path = urlparse(request.url)
        filename = os.path.basename(slide_path[2])

        slides = [slide for slide in self.root.get_screen('editor').slides_view.grid_layout.children]
        for slide in slides:
            img_src = urlparse(slide.img.img_src)
            if img_src[0] == 'http' and img_src[2].endswith(filename):
                Logger.debug('Application: Found slide ! Updating image source...')
                slide.img.img_src = os.path.join(self.tempdir, filename)
                Logger.debug('Application: {src}'.format(src=slide.img.img_src))
                slide.img.thumb_src = self.create_thumbnail(slide.img.img_src)
                slide.img.update_texture_size()
                self.update_presentation('update', 0, 0)
        self.root.current = 'editor'

    def get_flickr_url(self, photo, size):
        """construct a source url to a flickr photo.

        :param photo: photo information in json format.
        :param size: desired size of the photo :
            s	small square 75x75
            q	large square 150x150
            t	thumbnail, 100 on longest side
            m	small, 240 on longest side
            n	small, 320 on longest side
            -	medium, 500 on longest side
            z	medium 640, 640 on longest side
            c	medium 800, 800 on longest side†
            b	large, 1024 on longest side*
            o	original image, either a jpg, gif or png, depending on source format
        :return url:

        """
        url = 'https://farm{farm_id}.staticflickr.com/{server_id}/{id}_{secret}_{size}.jpg'
        url = url.format(farm_id=photo['farm'], server_id=photo['server'], id=photo['id'],
                         secret=photo['secret'], size=size)
        return url

    def search_term(self, term, engine, page):

        engines = {
            'met': ('http://www.metmuseum.org/'
                    'collection/the-collection-online/search'
                    '?ft={term}&ao=on&rpp={rpp}&pg={page}'),
            'getty': ('http://search.getty.edu/'
                      'gateway/search'
                      '?q={term}&cat=highlight&f="Open+Content+Images"&rows={rpp}&srt=&dir=s&dsp=0&img=0&pg={page}')
        }

        url = engines[engine].format(term=term,
                                     rpp=self.config.get('search', 'search_rpp'),
                                     page=page)
        clean_url = quote(url, safe="%/:=&?~#+!$,;'@()*[]")

        UrlRequest(clean_url, on_success=self.parse_results, debug=True)

    def parse_results(self, request, data):
        tree = html.fromstring(data)
        search_screen = self.root.get_screen('search')
        results = []

        if 'metmuseum' in urlparse(request.url).hostname:

            try:
                total_pages = tree.xpath(
                    '//li[starts-with(@id, "phcontent_0_phfullwidthcontent_0_paginationWidget_rptPagination_paginationLineItem_")]//a/text()')
                search_screen.box.total_pages = max([int(n) for n in total_pages])
            except ValueError:
                self.show_popup(_('Error'), _('No results found.'))
                return

            objects = tree.xpath('//div[starts-with(@class, "list-view-object ")]')

            for object in objects:
                result = {}
                result['title'] = object.xpath('./div[@class="list-view-object-info"]/a/div[@class="objtitle"]/text()')[
                    0]
                try:
                    result['artist'] = \
                        object.xpath('./div[@class="list-view-object-info"]/div[@class="artist"]/text()')[::2][0]
                except IndexError:
                    result['artist'] = 'Unknown'
                result['thumb'] = quote(object.xpath('./div[@class="list-view-thumbnail"]//img/@src')[0],
                                               safe="%/:=&?~#+!$,;'@()*[]")
                object_info = object.xpath('./div[@class="list-view-object-info"]/div[@class="objectinfo"]/text()')
                result['year'] = object_info[0].strip('Dates: ')
                results.append(result)

        elif 'getty' in urlparse(request.url).hostname:

            try:
                search_screen.box.total_pages = tree.xpath('//td[@class="cs-page"]//input/@count')[0]
                if int(re.sub("[^0-9]", "", tree.xpath('//strong[@id="cs-results-count"]//text()')[0])) == 0:
                    raise ValueError
            except ValueError:
                self.show_popup(_('Error'), _('No results found.'))
                return

            artists = tree.xpath(
                '//div[@class="cs-result-data-brief"]//td[* = "Creator:" or * = "Maker Name:"]/following-sibling::td[1]/p/text()')
            titles = tree.xpath(
                '//div[@class="cs-result-data-brief"]//td[* = "Title:" or * = "Primary Title:"]/following-sibling::td[1]/p[@class="cs-record-link"]/a/strong/text()')
            dates = tree.xpath(
                '//div[@class="cs-result-data-brief"]//td[* = "Date:"]/following-sibling::td[1]/p/text()')
            thumb = tree.xpath('//img[@class="cs-result-thumbnail"]/@src')
            obj_link = tree.xpath(
                '//div[@class="cs-result-data-brief"]//td[* = "Title:" or * = "Primary Title:"]/following-sibling::td[1]/p[@class="cs-record-link"]/a/@href')

            results = [{'title': a, 'artist': b, 'year': c, 'thumb': quote(d, safe="%/:=&?~#+!$,;'@()*[]"),
                        'obj_link': e}
                       for a, b, c, d, e in zip(titles, artists, dates, thumb, obj_link)]

        for photo in results:
            Logger.debug('Search (MET): Loading {url}'.format(url=photo['thumb']))
            image = ItemButton(photo=photo, source=photo['thumb'], keep_ratio=True)
            search_screen.box.grid.add_widget(image)

        search_screen.box.status = _('Page {page} on {total_page}').format(page=search_screen.box.current_page,
                                                                        total_page=search_screen.box.total_pages)

    def on_stop(self):
        self.config.set('editor', 'last_dir', None)
        try:
            shutil.rmtree(self.tempdir, ignore_errors=True)
        except:
            Logger.exception('Application: Removing temp dir failed.')
        # # TODO: Check changes and ask user to save.
        pass


class Manager(ScreenManager):
    def __init__(self, **kwargs):
        super(Manager, self).__init__(**kwargs)
        Window.bind(on_key_down=self._on_keyboard_down)

    def _on_keyboard_down(self, instance, key, scancode, codepoint, modifier, **kwargs):
        if key == 275 and self.current == 'viewer':
            self.get_screen('viewer').carousel.load_next(mode='next')
        elif key == 276 and self.current == 'viewer':
            self.get_screen('viewer').carousel.load_previous()
        elif key == 108 and modifier == ['ctrl'] and self.current == 'viewer':
            self.get_screen('viewer').carousel.current_slide.viewer.lock()
        elif key == 100 and modifier == ['ctrl'] and self.current == 'viewer':
            self.get_screen('viewer').carousel.current_slide.viewer.painter.canvas.clear()
        elif key == 9 and self.current == 'viewer':
            self.get_screen('viewer').dialog.to_switch = True
            self.get_screen('viewer').dialog.title = _('Switch to...')
            self.get_screen('viewer').dialog.open()


