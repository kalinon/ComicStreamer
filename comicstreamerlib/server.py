#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -*- mode: Python; tab-width: 4; indent-tabs-mode: nil; -*-
# Do not change the previous lines. See PEP 8, PEP 263.
"""
ComicStreamer main server classes

Copyright 2012-2014  Anthony Beville

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

	http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import mimetypes
import urllib.parse
from io import BytesIO

import tornado.escape
import tornado.ioloop
import tornado.web
from sqlalchemy.orm import subqueryload

try:
    from PIL import WebPImagePlugin
except:
    pass
import gzip
import dateutil.parser
import logging.handlers
import imghdr
import socket
import webbrowser
import re

from comicapi.comicarchive import *

import comicstreamerlib.csversion
import comicstreamerlib.utils
from comicstreamerlib.database import *
from comicstreamerlib.monitor import Monitor
from comicstreamerlib.folders import AppFolders
from comicstreamerlib.bookmarker import Bookmarker

from comicstreamerlib.library import Library

Image.MAX_IMAGE_PIXELS = None  # Removed image size limit for testing


# add webp test to imghdr in case it isn't there already
def my_test_webp(h):
    if h.startswith(b'RIFF') and h[8:12] == b'WEBP':
        return 'webp'


imghdr.tests.append(my_test_webp)


# to allow a blank username
def fix_username(username):
    try:
        return username + b"XX"
    except Exception as e:
        # logging.exception(e)
        # Fix for Python 3.5
        return (username + "XX").encode()


def custom_get_current_user(handler):
    user = handler.get_secure_cookie("user")
    if user:
        user = fix_username(user)
    return user


class BaseHandler(tornado.web.RequestHandler):
    @property
    def webroot(self):
        return self.application.webroot

    @property
    def library(self):
        return self.application.library

    def get_current_user(self):
        return custom_get_current_user(self)


class GenericAPIHandler(BaseHandler):
    def validateAPIKey(self):
        if self.application.config['security']['use_api_key']:
            api_key = self.get_argument(u"api_key", default="")
            if api_key == self.application.config['security']['api_key']:
                return True
            else:
                raise tornado.web.HTTPError(400)


class JSONResultAPIHandler(GenericAPIHandler):
    def setContentType(self):
        self.add_header("Content-type", "application/json; charset=UTF-8")

    def processPagingArgs(self, query):
        per_page = self.get_argument(u"per_page", default=None)
        offset = self.get_argument(u"offset", default=None)
        # offset and max_results should be processed last

        total_results = None
        if per_page is not None:
            total_results = query.distinct().count()
            try:
                max = int(per_page)
                if total_results > max:
                    query = query.limit(max)
            except Exception as e:
                logging.exception(e)
                pass

        if offset is not None:
            try:
                off = int(offset)
                query = query.offset(off)
            except Exception as e:
                logging.exception(e)
                pass

        return query, total_results

    def processComicQueryArgs(self, query):
        global order_desc

        def hasValue(obj):
            return obj is not None and obj != ""

        keyphrase_filter = self.get_argument(u"keyphrase", default=None)
        series_filter = self.get_argument(u"series", default=None)
        path_filter = self.get_argument(u"path", default=None)
        folder_filter = self.get_argument(u"folder", default="")
        title_filter = self.get_argument(u"title", default=None)
        start_filter = self.get_argument(u"start_date", default=None)
        end_filter = self.get_argument(u"end_date", default=None)
        added_since = self.get_argument(u"added_since", default=None)
        modified_since = self.get_argument(u"modified_since", default=None)
        lastread_since = self.get_argument(u"lastread_since", default=None)
        order = self.get_argument(u"order", default=None)
        character = self.get_argument(u"character", default=None)
        team = self.get_argument(u"team", default=None)
        location = self.get_argument(u"location", default=None)
        storyarc = self.get_argument(u"storyarc", default=None)
        volume = self.get_argument(u"volume", default=None)
        publisher = self.get_argument(u"publisher", default=None)
        credit_filter = self.get_argument(u"credit", default=None)
        tag = self.get_argument(u"tag", default=None)
        genre = self.get_argument(u"genre", default=None)

        if folder_filter != "":
            folder_filter = os.path.normcase(os.path.normpath(folder_filter))
            logging.info(folder_filter)

        person = None
        role = None
        if hasValue(credit_filter):
            credit_info = credit_filter.split(":")
            if len(credit_info[0]) != 0:
                person = credit_info[0]
                if len(credit_info) > 1:
                    role = credit_info[1]

        if hasValue(person):
            query = query.join(Credit).filter(
                Person.name.ilike(person.replace(
                    "*", "%"))).filter(Credit.person_id == Person.id)
            if role is not None:
                query = query.filter(Credit.role_id == Role.id).filter(
                    Role.name.ilike(role.replace("*", "%")))
            # query = query.filter( Comic.persons.contains(str(person).replace("*","%") ))

        if hasValue(keyphrase_filter):
            keyphrase_filter = str(keyphrase_filter).replace("*", "%")
            keyphrase_filter = "%" + keyphrase_filter + "%"
            query = query.filter(
                Comic.series.ilike(keyphrase_filter)
                | Comic.title.ilike(keyphrase_filter)
                | Comic.publisher.ilike(keyphrase_filter)
                | Comic.path.ilike(keyphrase_filter)
                | Comic.comments.ilike(keyphrase_filter)
                # | Comic.characters_raw.any(Character.name.ilike(keyphrase_filter))
                # | Comic.teams_raw.any(Team.name.ilike(keyphrase_filter))
                # | Comic.locations_raw.any(Location.name.ilike(keyphrase_filter))
                # | Comic.storyarcs_raw.any(StoryArc.name.ilike(keyphrase_filter))
                | Comic.persons_raw.any(Person.name.ilike(keyphrase_filter)))

        def addQueryOnScalar(query, obj_prop, filt):
            if hasValue(filt):
                filt = str(filt).replace("*", "%")
                return query.filter(obj_prop.ilike(filt))
            else:
                return query

        def addQueryOnList(query, obj_list, list_prop, filt):
            if hasValue(filt):
                filt = str(filt).replace("*", "%")
                return query.filter(obj_list.any(list_prop.ilike(filt)))
            else:
                return query

        query = addQueryOnScalar(query, Comic.series, series_filter)
        query = addQueryOnScalar(query, Comic.title, title_filter)
        query = addQueryOnScalar(query, Comic.path, path_filter)
        query = addQueryOnScalar(query, Comic.folder, folder_filter)
        query = addQueryOnScalar(query, Comic.publisher, publisher)
        query = addQueryOnList(query, Comic.characters_raw, Character.name,
                               character)
        query = addQueryOnList(query, Comic.generictags_raw, GenericTag.name,
                               tag)
        query = addQueryOnList(query, Comic.teams_raw, Team.name, team)
        query = addQueryOnList(query, Comic.locations_raw, Location.name,
                               location)
        query = addQueryOnList(query, Comic.storyarcs_raw, StoryArc.name,
                               storyarc)
        query = addQueryOnList(query, Comic.genres_raw, Genre.name, genre)
        # if hasValue(series_filter):
        #    query = query.filter( Comic.series.ilike(str(series_filter).replace("*","%") ))
        # if hasValue(title_filter):
        #    query = query.filter( Comic.title.ilike(str(title_filter).replace("*","%") ))
        # if hasValue(filename_filter):
        #    query = query.filter( Comic.path.ilike(str(filename_filter).replace("*","%") ))
        # if hasValue(publisher):
        #    query = query.filter( Comic.publisher.ilike(str(publisher).replace("*","%") ))
        # if hasValue(character):
        #    query = query.filter( Comic.characters_raw.any(Character.name.ilike(str(character).replace("*","%") )))
        # if hasValue(tag):
        #    query = query.filter( Comic.generictags.contains(str(tag).replace("*","%") ))
        # if hasValue(team):
        #    query = query.filter( Comic.teams.contains(str(team).replace("*","%") ))
        # if hasValue(location):
        #    query = query.filter( Comic.locations.contains(str(location).replace("*","%") ))
        # if hasValue(storyarc):
        #    query = query.filter( Comic.storyarcs.contains(str(storyarc).replace("*","%") ))
        # if hasValue(genre):
        #    query = query.filter( Comic.genres.contains(str(genre).replace("*","%") ))
        if hasValue(volume):
            try:
                vol = int(volume)
                query = query.filter(Comic.volume == vol)
            except Exception as e:
                logging.exception(e)
                pass

        if hasValue(start_filter):
            try:
                dt = dateutil.parser.parse(start_filter)
                query = query.filter(Comic.date >= dt)
            except Exception as e:
                logging.exception(e)
                pass

        if hasValue(end_filter):
            try:
                dt = dateutil.parser.parse(end_filter)
                query = query.filter(Comic.date <= dt)
            except Exception as e:
                logging.exception(e)
                pass

        if hasValue(modified_since):
            try:
                # noinspection PyUnusedLocal
                dt = dateutil.parser.parse(modified_since)
            except Exception as e:
                logging.exception(e)
                pass

        if hasValue(added_since):
            try:
                dt = dateutil.parser.parse(added_since)
                query = query.filter(Comic.added_ts >= dt)
            except Exception as e:
                logging.exception(e)
                pass

        if hasValue(lastread_since):
            try:
                dt = dateutil.parser.parse(lastread_since)
                query = query.filter(Comic.lastread_ts >= dt,
                                     Comic.lastread_ts != "")
            except Exception as e:
                logging.exception(e)
                pass

        order_key = None
        # ATB temp hack to cover "slicing" bug where
        # if no order specified, the child collections
        # get chopped off sometimes
        if not hasValue(order):
            order = "id"

        if hasValue(order):
            if order[0] == "-":
                order_desc = True
                order = order[1:]
            else:
                order_desc = False
            if order == "id":
                order_key = Comic.id
            if order == "series":
                order_key = Comic.series
            elif order == "modified":
                order_key = Comic.mod_ts
            elif order == "added":
                order_key = Comic.added_ts
            elif order == "lastread":
                order_key = Comic.lastread_ts
            elif order == "volume":
                order_key = Comic.volume
            elif order == "issue":
                order_key = Comic.issue_num
            elif order == "date":
                order_key = Comic.date
            elif order == "publisher":
                order_key = Comic.publisher
            elif order == "title":
                order_key = Comic.title
            elif order == "path":
                order_key = Comic.path

        if order_key is not None:
            if order_desc:
                order_key = order_key.desc()
            query = query.order_by(order_key)

        return query


class ZippableAPIHandler(JSONResultAPIHandler):
    def writeResults(self, json_data):
        self.setContentType()
        if self.get_argument(u"gzip", default=None) is not None:
            self.add_header("Content-Encoding", "gzip")
            # TODO: make sure browser can handle gzip?
            zbuf = StringIO()
            zfile = gzip.GzipFile(mode='wb', fileobj=zbuf, compresslevel=9)
            zfile.write(json.dumps(json_data))
            zfile.close()

            self.write(zbuf.getvalue())
        else:
            self.write(json_data)


class CommandAPIHandler(GenericAPIHandler):
    def get(self):
        self.validateAPIKey()
        cmd = self.get_argument(u"cmd", default=None)
        if cmd == "restart":
            logging.info("Restart command")
            self.application.restart()
        elif cmd == "reset":
            logging.info("Rebuild DB command")
            self.application.rebuild()
        elif cmd == "stop":
            logging.info("Stop command")
            self.application.shutdown()


class ImageAPIHandler(GenericAPIHandler):
    def setContentType(self, image_data):
        if type(image_data) is bytes:
            imtype = imghdr.what(BytesIO(image_data))
            self.add_header("Content-type", "image/{0}".format(imtype))
        else:
            self.add_header("Content-type", "image/{0}".format(image_data))


class VersionAPIHandler(JSONResultAPIHandler):
    def get(self):
        self.validateAPIKey()
        response = {
            'version': self.application.version,
            'last_build': date.today().isoformat()
        }
        self.setContentType()
        self.write(response)


class DBInfoAPIHandler(JSONResultAPIHandler):
    def get(self):
        self.validateAPIKey()
        stats = self.library.getStats()
        response = {
            'id': stats['uuid'],
            'last_updated': stats['last_updated'].isoformat(),
            'created': stats['created'].isoformat(),
            'comic_count': stats['total']
        }
        self.setContentType()
        self.write(response)


class ScanStatusAPIHandler(JSONResultAPIHandler):
    def get(self):
        self.validateAPIKey()
        status = self.application.monitor.status
        detail = self.application.monitor.statusdetail
        last_complete = self.application.monitor.scancomplete_ts

        response = {
            'status': status,
            'detail': detail,
            'last_complete': last_complete,
            'current_time': int(
                time.mktime(datetime.utcnow().timetuple()) * 1000),
        }
        self.setContentType()
        self.write(response)


class ComicListAPIHandler(ZippableAPIHandler):
    def get(self):
        self.validateAPIKey()

        criteria_args = [
            u"keyphrase", u"series", u"path", u"folder", u"title",
            u"start_date", u"end_date", u"added_since", u"modified_since",
            u"lastread_since", u"order", u"character", u"team", u"location",
            u"storyarc", u"volume", u"publisher", u"credit", u"tag", u"genre"
        ]

        criteria = {
            key: self.get_argument(key, default=None)
            for key in criteria_args
        }
        paging = {
            'per_page': self.get_argument(u"per_page", default=None),
            'offset': self.get_argument(u"offset", default=None)
        }

        if criteria['series'] is not None:
            m = re.search('\s-\sv(\d+)', criteria[u"series"])
            if m is not None:
                volume = m.group(1)
                criteria['volume'] = volume
                criteria['series'] = re.sub('\s-\sv(\d+)', '', criteria['series'])

        logging.info(criteria)

        resultset, total_results = self.library.list(criteria, paging)

        json_data = resultSetToJson(resultset, "comics", total_results)

        self.writeResults(json_data)


class DeletedAPIHandler(ZippableAPIHandler):
    def get(self):
        self.validateAPIKey()

        since_filter = self.get_argument(u"since", default=None)
        resultset = self.library.getDeletedComics(since_filter)

        json_data = resultSetToJson(resultset, "deletedcomics")

        self.writeResults(json_data)


class ComicListBrowserHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):

        entity_src = self.get_argument(u"entity_src", default=None)
        if entity_src is not None:
            src = entity_src
        else:
            default_src = self.webroot + "/comiclist"
            arg_string = ""
            ##if '?' in self.request.uri:
            #    arg_string = '?'+self.request.uri.split('?',1)[1]
            src = default_src + arg_string

        self.render(
            "comic_results2.html",
            src=src,
            api_key=self.application.config['security']['api_key'])


class FoldersBrowserHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, args):
        if args is None:
            args = "/"
        args = comicstreamerlib.utils.collapseRepeats(args, "/")

        self.render(
            "folders.html",
            args=args,
            api_key=self.application.config['security']['api_key'])


class EntitiesBrowserHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, args):
        if args is None:
            args = ""
        arg_string = args
        # if '/' in args:
        #   arg_string = args.split('/',1)[1]
        # print arg_string
        # if len(arg_string) == 0:
        #    arg_string = "?api_key=" + self.application.config['security']['api_key']
        # else:
        #    arg_string = arg_string + "&api_key=" + self.application.config['security']['api_key']

        self.render(
            "entities.html",
            args=arg_string,
            api_key=self.application.config['security']['api_key'])


class ComicAPIHandler(JSONResultAPIHandler):
    def get(self, id):
        self.validateAPIKey()

        result = [self.library.getComic(id)]

        self.setContentType()
        self.write(resultSetToJson(result, "comics"))


class ComicBookmarkAPIHandler(JSONResultAPIHandler):
    def get(self, comic_id, pagenum):
        self.validateAPIKey()

        self.application.bookmarker.setBookmark(comic_id, pagenum)

        self.setContentType()
        response = {'status': 0}
        self.write(response)


class ComicPageAPIHandler(ImageAPIHandler):
    def get(self, comic_id, pagenum):
        self.validateAPIKey()

        max_height = self.get_argument(u"max_height", default=None)

        image_data = self.library.getComicPage(comic_id, pagenum, max_height)

        self.setContentType(image_data)
        self.write(image_data)


class ThumbnailAPIHandler(ImageAPIHandler):
    def get(self, comic_id):
        self.validateAPIKey()
        thumbnail = self.library.getComicThumbnail(comic_id)

        if thumbnail is not None:
            self.setContentType('image/jpg')
            self.write(thumbnail)
        else:
            default_img_file = AppFolders.imagePath("default.jpg")
            with open(default_img_file, 'rb') as fd:
                image_data = fd.read()
            self.setContentType('image/jpg')
            self.write(image_data)


class FileAPIHandler(GenericAPIHandler):
    def get(self, comic_id):
        self.validateAPIKey()

        obj = self.library.getComic(comic_id)
        if obj is not None:
            (content_type, encoding) = mimetypes.guess_type(obj.path)
            if content_type is None:
                content_type = "application/octet-stream"

            self.add_header("Content-type", content_type)
            self.add_header(
                "Content-Disposition",
                "attachment; filename=" + os.path.basename(obj.path))

            # stream response in chunks, cbr/z could be over 300MB in size!
            # TODO: check it doesn't buffer the response, it should send data chunk by chunk
            with open(obj.path, 'rb') as f:
                while True:
                    data = f.read(40960 * 1024)
                    if not data:
                        break
                    self.write(data)
                    self.flush()
            self.finish()


class FolderAPIHandler(JSONResultAPIHandler):
    def get(self, args):
        self.validateAPIKey()
        if args is not None:
            args = urllib.parse.unquote(args)
            arglist = args.split('/')
            arglist = list(filter(None, arglist))
            argcount = len(arglist)
        else:
            arglist = list()
            argcount = 0

        folder_list = self.application.config['general']['folder_list']

        response = {
            'current': "",
            'folders': [],
            'comics': {
                'url_path': "",
                'count': 0
            }
        }
        if argcount == 0:
            # just send the list of root level folders
            for idx, val in enumerate(folder_list):
                item = {
                    'name': val,
                    'url_path': self.webroot + "/folders/" + str(idx)
                }
                response['folders'].append(item)

        else:
            try:
                # need to validate the first arg is an index into the list
                folder_idx = int(arglist[0])
                if folder_idx >= len(folder_list):
                    raise Exception

                # build up a folder by combining the root folder with the following path
                path = os.path.join(folder_list[folder_idx], *arglist[1:])
                # validate *that* folder
                if not os.path.exists(path):
                    logging.error("Not exist", path, type(path))
                    raise Exception

                response['current'] = path
                # create a list of subfolders
                for o in os.listdir(path):
                    if os.path.isdir(os.path.join(path, o)):
                        sub_path = u"/folders" + args + u"/" + o
                        sub_path = urllib.parse.quote(sub_path.encode("utf-8"))
                        item = {'name': o, 'url_path': sub_path}
                        response['folders'].append(item)
                # see if there are any comics here
                (ignore, total_results) = self.library.list({'folder': path}, {
                    'per_page': 0,
                    'offset': 0
                })
                response['comics']['count'] = total_results
                comic_path = self.webroot + u"/comiclist?folder=" + urllib.parse.quote(
                    u"{0}".format(path).encode('utf-8'))
                response['comics']['url_path'] = comic_path

            except FloatingPointError as e:
                logging.error(e)
                raise tornado.web.HTTPError(404, "Unknown folder")

        self.setContentType()
        self.write(response)


class EntityAPIHandler(JSONResultAPIHandler):
    def get(self, args):
        self.validateAPIKey()
        session = self.application.dm.Session()

        if args is None:
            args = ""
        arglist = args.split('/')

        arglist = list(filter(None, arglist))
        argcount = len(arglist)

        entities = {
            'characters': Character.name,
            'persons': Person.name,
            'publishers': Comic.publisher,
            'roles': Role.name,
            'series': Comic.series,
            'volumes': Comic.volume,
            'teams': Team.name,
            'storyarcs': StoryArc.name,
            'genres': Genre.name,
            'locations': Location.name,
            'generictags': GenericTag.name,
            'comics': Comic
        }
        logging.info("In EntityAPIHandler {0}".format(arglist))
        # /entity1/filter1/entity2/filter2...

        # validate all entities keys in args
        # ( check every other item)
        for e in arglist[0::2]:
            if e not in entities:
                raise tornado.web.HTTPError(404, "Unknown entity:{0}".format(e))
        # look for dupes
        if len(arglist[0::2]) != len(set(arglist[0::2])):
            raise tornado.web.HTTPError(400, "Duplicate entity")
        # look for dupes
        if 'comics' in arglist[0::2] and arglist[-1] != "comics":
            raise tornado.web.HTTPError(400, "\"comics\" must be final entity")

        # even number means listing entities
        if argcount % 2 == 0:
            name_list = [key for key in entities]
            logging.info("In EntityAPIHandler names {0}".format(name_list))

            # (remove already-traversed entities)
            for e in arglist[0::2]:
                try:
                    name_list.remove(e)
                except Exception as e:
                    logging.exception(e)
                    pass

            # Find out how many of each entity are left, and build a list of
            # dicts with name and count
            dict_list = []
            for e in name_list:
                tmp_arg_list = list()
                tmp_arg_list.extend(arglist)
                tmp_arg_list.append(e)
                query = self.buildQuery(session, entities, tmp_arg_list)
                e_dict = dict()
                e_dict['name'] = e
                # self.application.dm.engine.echo = True
                e_dict['count'] = query.distinct().count()
                # self.application.dm.engine.echo = False
                # print "----", e_dict, query
                dict_list.append(e_dict)

            # name_list = sorted(name_list)

            resp = {"entities": dict_list}
            self.setContentType()
            self.write(resp)
            return

        # odd number means listing last entity VALUES
        else:
            entity = arglist[-1]  # the final entity in the list
            query = self.buildQuery(session, entities, arglist)

            logging.info("query {0}".format(query))

            if entity == "comics":

                query = self.processComicQueryArgs(query)
                query, total_results = self.processPagingArgs(query)

                query = query.options(subqueryload('characters_raw'))
                query = query.options(subqueryload('storyarcs_raw'))
                query = query.options(subqueryload('locations_raw'))
                query = query.options(subqueryload('teams_raw'))
                # query = query.options(subqueryload('credits_raw'))
                query = query.options(subqueryload('generictags_raw'))
                query = query.all()
                resp = resultSetToJson(query, "comics", total_results)
            else:
                _entities = []
                for i in query.all():
                    val = i[0]
                    if entity == 'series' and i[1] is not None:
                        val = "{0} - v{1}".format(i[0], i[1])
                    # logging.info(val)

                    if val is not None and val not in _entities:
                        _entities.append(val)

                resp = {entity: sorted(_entities)}
            self.application.dm.engine.echo = False

        self.setContentType()
        self.write(resp)

    def buildQuery(self, session, entities, arglist):
        """
         Each entity-filter pair will be made into a separate query
         and they will be all intersected together
        """

        entity = arglist[-1]
        querylist = []

        # To build up the query, bridge every entity to a comic table

        if entity == 'series':
            querybase = session.query(entities[entity], entities["volumes"])
        else:
            querybase = session.query(entities[entity])

        logging.debug("querybase {0}".format(querybase))
        if len(arglist) != 1:
            if entity == 'roles':
                querybase = querybase.join(Credit).join(Comic)
            if entity == 'persons':
                querybase = querybase.join(Credit).join(Comic)
            if entity == 'characters':
                querybase = querybase.join(comics_characters_table).join(Comic)
            if entity == 'teams':
                querybase = querybase.join(comics_teams_table).join(Comic)
            if entity == 'storyarcs':
                querybase = querybase.join(comics_storyarcs_table).join(Comic)
            if entity == 'genres':
                querybase = querybase.join(comics_genres_table).join(Comic)
            if entity == 'locations':
                querybase = querybase.join(comics_locations_table).join(Comic)
            if entity == 'generictags':
                querybase = querybase.join(comics_generictags_table).join(Comic)

        # print "Result entity is====>", entity
        # iterate over list, 2 at a time, building query list,
        # print zip(arglist[0::2], arglist[1::2])
        for e, v in zip(arglist[0::2], arglist[1::2]):
            # print "--->",e,v
            query = querybase
            if e == 'roles':
                if entity != 'persons':
                    query = query.join(Credit)
                query = query.join(Role)
            if e == 'persons':
                if entity != 'roles':
                    query = query.join(Credit)
                query = query.join(Person)
            if e == 'characters':
                query = query.join(comics_characters_table).join(Character)
            if e == 'teams':
                query = query.join(comics_teams_table).join(Team)
            if e == 'storyarcs':
                query = query.join(comics_storyarcs_table).join(StoryArc)
            if e == 'genres':
                query = query.join(comics_genres_table).join(Genre)
            if e == 'locations':
                query = query.join(comics_locations_table).join(Location)
            if e == 'generictags':
                query = query.join(comics_generictags_table).join(GenericTag)
            query = query.filter(entities[e] == v)
            querylist.append(query)
            # print query

        if len(querylist) == 0:
            finalquery = querybase
        else:
            finalquery = querylist[0].intersect(*querylist[1:])

        return finalquery


class ReaderHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, comic_id):

        obj = self.library.getComic(comic_id)
        if obj is not None:
            # self.render("templates/reader.html", make_list=self.make_list, id=comic_id, count=obj.page_count)
            # self.render("test.html", make_list=self.make_list, id=comic_id, count=obj.page_count)

            title = os.path.basename(obj.path)
            if obj.series is not None and obj.issue is not None:
                title = obj.series + u" #" + obj.issue
                if obj.title is not None:
                    title += u" -- " + obj.title
            if obj.lastread_page is None:
                target_page = 0
            else:
                target_page = obj.lastread_page

            self.render(
                "cbreader.html",
                title=title,
                id=comic_id,
                count=obj.page_count,
                page=target_page,
                api_key=self.application.config['security']['api_key'])


class UnknownHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.write("Whoops! Four-oh-four.")


class MainHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        stats = self.library.getStats()
        stats['last_updated'] = comicstreamerlib.utils.utc_to_local(
            stats['last_updated']).strftime("%Y-%m-%d %H:%M:%S")
        stats['created'] = comicstreamerlib.utils.utc_to_local(
            stats['created']).strftime("%Y-%m-%d %H:%M:%S")

        recently_added_comics = self.library.recentlyAddedComics(10)
        recently_read_comics = self.library.recentlyReadComics(10)
        roles_list = [role.name for role in self.library.getRoles()]
        random_comic = self.library.randomComic()

        if random_comic is None:
            random_comic = type('fakecomic', (object,), {
                'id': 0,
                'series': 'No Comics',
                'issue': 0
            })()

        self.render(
            "index.html",
            stats=stats,
            random_comic=random_comic,
            recently_added=list(recently_added_comics),
            recently_read=list(recently_read_comics),
            roles=roles_list,
            server_time=int(time.mktime(datetime.utcnow().timetuple()) * 1000),
            api_key=self.application.config['security']['api_key'])


class GenericPageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, page):
        self.render(page + ".html")


class AboutPageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("about.html", version=self.application.version)


class ControlPageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render(
            "control.html",
            api_key=self.application.config['security']['api_key'])


class LogPageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        log_file = os.path.join(AppFolders.logs(), "ComicStreamer.log")

        logtxt = ""
        for line in reversed(open(log_file).readlines()):
            logtxt += line.rstrip() + '\n'

        self.render("log.html", logtxt=logtxt)


class ConfigPageHandler(BaseHandler):
    fakepass = "N0TRYL@P@SSWRD"

    def is_port_available(self, port):
        host = '127.0.0.1'

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect((host, port))
            s.shutdown(2)
            return False
        except Exception as e:
            logging.error(e)
            return True

    def render_config(self, formdata, success="", failure=""):
        # convert boolean to "checked" or ""
        formdata['use_api_key'] = "checked" if formdata['use_api_key'] else ""
        formdata['use_authentication'] = "checked" if formdata[
            'use_authentication'] else ""
        formdata[
            'launch_browser'] = "checked" if formdata['launch_browser'] else ""

        if self.application.config['security']['use_authentication']:
            formdata['password'] = ConfigPageHandler.fakepass
            formdata['password_confirm'] = ConfigPageHandler.fakepass
        else:
            formdata['password'] = ""
            formdata['password_confirm'] = ""

        self.render(
            "configure.html",
            formdata=formdata,
            success=success,
            failure=failure)

    @tornado.web.authenticated
    def get(self):
        formdata = dict()
        formdata['port'] = self.application.config['general']['port']
        formdata['webroot'] = self.application.config['general']['webroot']
        formdata['folders'] = "\n".join(
            self.application.config['general']['folder_list'])
        formdata['use_authentication'] = self.application.config['security'][
            'use_authentication']
        formdata['username'] = self.application.config['security']['username']
        formdata['password'] = ""
        formdata['password_confirm'] = ""
        formdata['use_api_key'] = self.application.config['security'][
            'use_api_key']
        formdata['api_key'] = self.application.config['security']['api_key']
        formdata['launch_browser'] = self.application.config['general'][
            'launch_browser']

        self.render_config(formdata)

    @tornado.web.authenticated
    def post(self):
        global new_port
        formdata = dict()
        formdata['port'] = self.get_argument(u"port", default="")
        formdata['webroot'] = self.get_argument(u"webroot", default="")
        formdata['folders'] = self.get_argument(u"folders", default="")
        formdata['use_authentication'] = (len(
            self.get_arguments("use_authentication")) != 0)
        formdata['username'] = self.get_argument(u"username", default="")
        formdata['password'] = self.get_argument(u"password", default="")
        formdata['password_confirm'] = self.get_argument(
            u"password_confirm", default="")
        formdata['use_api_key'] = (len(self.get_arguments("use_api_key")) != 0)
        formdata['api_key'] = self.get_argument(u"api_key", default="")
        formdata['launch_browser'] = (len(
            self.get_arguments("launch_browser")) != 0)

        failure_str = ""
        success_str = ""
        failure_strs = list()
        validated = False

        old_folder_list = self.application.config['general']['folder_list']
        new_folder_list = [
            os.path.normcase(os.path.abspath(os.path.normpath(str(a))))
            for a in formdata['folders'].splitlines()
        ]

        try:
            for i, f in enumerate(new_folder_list):
                # validate folders exist
                if not (os.path.exists(f) and os.path.isdir(f)):
                    failure_strs.append(u"Folder {0} doesn't exist.".format(f))
                    break
                # check for repeat or contained
                for j, f1 in enumerate(new_folder_list):
                    if i != j:
                        if f1 == f:
                            failure_strs.append(u"Can't have repeat folders.")
                            raise Exception
                        if f1.startswith(f + os.path.sep):
                            failure_strs.append(
                                u"One folder can't contain another.")
                            raise Exception
        except Exception:
            pass

        port_failed = False
        old_port = self.application.config['general']['port']

        # validate numeric port
        if not formdata['port'].isdigit():
            port_failed = True
            failure_strs.append(u"Non-numeric port value: {0}".format(
                formdata['port']))

        # validate port range
        if not port_failed:
            new_port = int(formdata['port'])
            if new_port > 49151 or new_port < 1024:
                failure_strs.append(
                    u"Port value out of range (1024-4151): {0}".format(
                        new_port))
                port_failed = True

        # validate port availability
        if not port_failed:
            if new_port != old_port and not self.is_port_available(new_port):
                failure_strs.append(
                    u"Port not available: {0}".format(new_port))

        # validate password and username are set
        if formdata['use_authentication'] and (formdata['username'] == ""
                                               or formdata['password'] == ""):
            failure_strs.append(
                u"Username and password must be filled in if the 'use authentication' box is checked"
            )

        # validate password pair is the same
        if formdata['password'] != formdata['password_confirm']:
            failure_strs.append(u"Password fields don't match.")

        if formdata['use_api_key'] and formdata['api_key'] == "":
            failure_strs.append(
                u"API Key must have a value if the box is checked")

        if len(failure_strs) == 0:
            validated = True

        if validated:
            # was the password changed?
            password_changed = True
            if formdata['use_authentication']:
                if formdata['password'] == ConfigPageHandler.fakepass:
                    password_changed = False
                elif comicstreamerlib.utils.getDigest(
                        formdata['password']
                ) == self.application.config['security']['password_digest']:
                    password_changed = False
            else:
                password_changed = False

            # find out if we need to save:
            if (new_port != old_port or formdata['webroot'] !=
                    self.application.config['general']['webroot']
                    or new_folder_list != old_folder_list
                    or formdata['username'] !=
                    self.application.config['security']['username']
                    or password_changed or formdata['use_api_key'] !=
                    self.application.config['security']['use_api_key']
                    or formdata['api_key'] !=
                    self.application.config['security']['api_key']
                    or formdata['launch_browser'] !=
                    self.application.config['general']['launch_browser']):
                # apply everything from the form
                self.application.config['general'][
                    'folder_list'] = new_folder_list
                self.application.config['general']['port'] = new_port
                self.application.config['general']['webroot'] = formdata[
                    'webroot']
                self.application.config['security'][
                    'use_authentication'] = formdata['use_authentication']
                self.application.config['security']['username'] = formdata[
                    'username']
                if formdata['password'] != ConfigPageHandler.fakepass:
                    self.application.config['security'][
                        'password_digest'] = comicstreamerlib.utils.getDigest(
                        formdata['password'])
                self.application.config['security']['use_api_key'] = formdata[
                    'use_api_key']
                if self.application.config['security']['use_api_key']:
                    self.application.config['security']['api_key'] = formdata[
                        'api_key']
                else:
                    self.application.config['security']['api_key'] = ""
                    formdata['api_key'] = ""
                self.application.config['general'][
                    'launch_browser'] = formdata['launch_browser']

                success_str = "Saved. Server restart needed"
                self.application.config.write()
        else:
            failure_str = "<br/>".join(failure_strs)
        formdata['password'] = ""
        formdata['password_confirm'] = ""
        logging.info("Config: " + str(self.application.config))
        self.render_config(formdata, success=success_str, failure=failure_str)


class LoginHandler(BaseHandler):
    def get(self):
        if len(self.get_arguments("next")) != 0:
            next = self.get_argument("next")
        else:
            next = self.webroot + "/"

        # if password and user are blank, just skip to the "next"
        if (self.application.config['security']['password_digest'] ==
                comicstreamerlib.utils.getDigest("")
                and self.application.config['security']['username'] == ""):
            self.set_secure_cookie(
                "user",
                fix_username(self.application.config['security']['username']))
            self.redirect(next)
        else:
            self.render('login.html', next=next)

    def post(self):
        next = self.get_argument("next")

        if len(self.get_arguments("password")) != 0:

            # print self.application.password, self.get_argument("password") , next
            if (comicstreamerlib.utils.getDigest(
                    self.get_argument("password")) ==
                    self.application.config['security']['password_digest']
                    and self.get_argument("username") ==
                    self.application.config['security']['username']):
                # self.set_secure_cookie("auth", self.application.config['security']['password_digest'])
                self.set_secure_cookie(
                    "user",
                    fix_username(
                        self.application.config['security']['username']))

        self.redirect(next)


class APIServer(tornado.web.Application):
    def __init__(self, config, opts):
        comicstreamerlib.utils.fix_output_encoding()

        self.config = config
        self.opts = opts

        self.port = self.config['general']['port']
        self.webroot = self.config['general']['webroot']

        self.comicArchiveList = []

        # if len(self.config['general']['folder_list']) == 0:
        #    logging.error("No folders on either command-line or config file.  Quitting.")
        #    sys.exit(-1)

        self.dm = DataManager()
        self.library = Library(self.dm.Session)

        if opts.reset or opts.reset_and_run:
            logging.info("Deleting any existing database!")
            self.dm.delete()

        # quit on a standard reset
        if opts.reset:
            sys.exit(0)

        try:
            self.dm.create()
        except SchemaVersionException:
            msg = "Couldn't open database.  Probably the schema has changed."
            logging.error(msg)
            comicstreamerlib.utils.alert("Schema change", msg)
            sys.exit(-1)

        try:
            self.listen(self.port, no_keep_alive=True)
        except Exception as e:
            logging.error(e)
            msg = "Couldn't open socket on port {0}. (Maybe ComicStreamer is already running?) Quitting.".format(
                self.port)
            logging.error(msg)
            comicstreamerlib.utils.alert("Port not available", msg)
            sys.exit(-1)

        logging.info("Stream server running on port {0}...".format(self.port))

        # http_server = tornado.httpserver.HTTPServer(self, no_keep_alive = True, ssl_options={
        #    "certfile": "server.crt",
        #    "keyfile": "server.key",
        # })
        # http_server.listen(port+1)

        self.version = comicstreamerlib.csversion.version

        handlers = [
            # Web Pages
            (self.webroot + r"/", MainHandler),
            (self.webroot + r"/(.*)\.html", GenericPageHandler),
            (self.webroot + r"/about", AboutPageHandler),
            (self.webroot + r"/control", ControlPageHandler),
            (self.webroot + r"/configure", ConfigPageHandler),
            (self.webroot + r"/log", LogPageHandler),
            (self.webroot + r"/comiclist/browse", ComicListBrowserHandler),
            (self.webroot + r"/folders/browse(/.*)*", FoldersBrowserHandler),
            (self.webroot + r"/entities/browse(/.*)*", EntitiesBrowserHandler),
            (self.webroot + r"/comic/([0-9]+)/reader", ReaderHandler),
            (self.webroot + r"/login", LoginHandler),
            # Data
            (self.webroot + r"/dbinfo", DBInfoAPIHandler),
            (self.webroot + r"/version", VersionAPIHandler),
            (self.webroot + r"/deleted", DeletedAPIHandler),
            (self.webroot + r"/comic/([0-9]+)", ComicAPIHandler),
            (self.webroot + r"/comiclist", ComicListAPIHandler),
            (self.webroot + r"/comic/([0-9]+)/page/([0-9]+|clear)/bookmark", ComicBookmarkAPIHandler),
            (self.webroot + r"/comic/([0-9]+)/page/([0-9]+)", ComicPageAPIHandler),
            (self.webroot + r"/comic/([0-9]+)/thumbnail", ThumbnailAPIHandler),
            (self.webroot + r"/comic/([0-9]+)/file", FileAPIHandler),
            (self.webroot + r"/entities(/.*)*", EntityAPIHandler),
            (self.webroot + r"/folders(/.*)*", FolderAPIHandler),
            (self.webroot + r"/command", CommandAPIHandler),
            (self.webroot + r"/scanstatus", ScanStatusAPIHandler),
            # (r'/favicon.ico', tornado.web.StaticFileHandler, {'path': os.path.join(AppFolders.appBase(), "static","images")}),
            (self.webroot + r'/.*', UnknownHandler),
        ]

        settings = dict(
            template_path=os.path.join(AppFolders.appBase(), "templates"),
            static_path=os.path.join(AppFolders.appBase(), "static"),
            static_url_prefix=self.webroot + "/static/",
            debug=True,
            # autoreload=False,
            login_url=self.webroot + "/login",
            cookie_secret=self.config['security']['cookie_secret'],
            xsrf_cookies=True,
        )

        tornado.web.Application.__init__(self, handlers, **settings)

        if not opts.no_monitor:
            logging.debug("Going to scan the following folders:")
            for l in self.config['general']['folder_list']:
                logging.debug(u"   {0}".format(repr(l)))

            self.monitor = Monitor(self.dm,
                                   self.config['general']['folder_list'])
            self.monitor.start()
            self.monitor.scan()

        self.bookmarker = Bookmarker(self.dm)
        self.bookmarker.start()

        if opts.launch_browser and self.config['general']['launch_browser']:
            if ((platform.system() == "Linux" and ('DISPLAY' in os.environ))
                    or (platform.system() == "Darwin"
                        and not ('SSH_TTY' in os.environ))
                    or platform.system() == "Windows"):
                webbrowser.open(
                    "http://localhost:{0}".format(self.port), new=0)

    def rebuild(self):
        # after restart, purge the DB
        sys.argv.insert(1, "--_resetdb_and_run")
        self.restart()

    def restart(self):
        self.shutdown()
        executable = sys.executable

        new_argv = ["--nobrowser"]
        if self.opts.quiet:
            new_argv.append("-q")
        if self.opts.debug:
            new_argv.append("-d")
        if "--_resetdb_and_run" in sys.argv:
            new_argv.append("--_resetdb_and_run")

        if getattr(sys, 'frozen', None):
            # only keep selected args
            new_argv.insert(0, os.path.basename(executable))
            os.execv(executable, new_argv)
        else:
            new_argv.insert(0, os.path.basename(sys.argv[0]))
            os.execl(executable, executable, *new_argv)

    def shutdown(self):

        MAX_WAIT_SECONDS_BEFORE_SHUTDOWN = 3

        logging.info('Initiating shutdown...')
        self.monitor.stop()
        self.bookmarker.stop()

        logging.info('Will shutdown ComicStreamer in maximum %s seconds ...',
                     MAX_WAIT_SECONDS_BEFORE_SHUTDOWN)
        io_loop = tornado.ioloop.IOLoop.instance()

        deadline = time.time() + MAX_WAIT_SECONDS_BEFORE_SHUTDOWN

        def stop_loop():
            now = time.time()
            if now < deadline:
                io_loop.add_timeout(now + 1, stop_loop)
            else:
                io_loop.stop()
                logging.info('Shutdown complete.')

        stop_loop()

    def log_request(self, handler):
        if handler.get_status() < 300:
            log_method = logging.debug
        elif handler.get_status() < 400:
            log_method = logging.debug
        elif handler.get_status() < 500:
            log_method = logging.warning
        else:
            log_method = logging.error
        request_time = 1000.0 * handler.request.request_time()
        log_method("%d %s %.2fms", handler.get_status(), handler._request_summary(), request_time)

    def run(self):
        try:
            tornado.ioloop.IOLoop.instance().start()
        except Exception as e:
            logging.exception(e)

    def runInThread(self):
        import threading
        t = threading.Thread(target=self.run)
        t.start()
