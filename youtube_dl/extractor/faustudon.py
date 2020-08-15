# coding: utf-8
from __future__ import unicode_literals

from .common import InfoExtractor
from ..utils import RegexNotFoundError, clean_html

import base64
import re
import json
import typing


class FauStudonContentGroupIE(InfoExtractor):
    """
    A content group is a set of one or more videos, all stored under the same URL. Which video is shown is stored on the
    server side.
    """

    _VALID_URL = r'https://www\.studon\.fau\.de/studon/ilias\.php\?ref_id=(?P<id>\d+)&cmd=showContents&cmdClass=ilobjh5pgui&cmdNode=qu:pb&baseClass=ilObjPluginDispatchGUI'

    _JS_BASE64_PATTERN = re.compile(r'<script type="text/javascript" src="data:application/javascript;base64,([^"]+)')

    @staticmethod
    def _switch_page_link(contents_id: int, prev: bool):
        return "ilias.php?ref_id=" + \
               str(contents_id) + "&cmd=" + ("previous" if prev else "next") + \
               "Content&cmdClass=ilobjh5pgui&cmdNode=qu:pb&baseClass=ilObjPluginDispatchGUI"

    def _switch_page(self, contents_id: int, prev: bool):
        self._download_webpage("https://www.studon.fau.de/studon/" + self._switch_page_link(contents_id, prev),
                               video_id=str(contents_id),
                               expected_status=302)

    def _real_extract(self, url):
        contents_id = self._match_id(url)

        collected_videos = []
        grand_title = None

        def fetch_one(prepend: bool) -> typing.Tuple[bool, bool]:
            webpage = self._download_webpage(url, contents_id)

            result1 = FauStudonContentGroupIE._JS_BASE64_PATTERN.search(webpage)
            if result1 is None:
                raise RegexNotFoundError("Unable to extract integration blob (1). Are you authenticated?")
            result2 = FauStudonContentGroupIE._JS_BASE64_PATTERN.search(webpage, result1.end())
            if result2 is None:
                raise RegexNotFoundError("Unable to extract integration blob (2). Are you authenticated?")

            integration_script = base64.decodebytes(result2.group(1).encode("utf-8")).decode("utf-8")
            result = re.match(r'H5PIntegration.contents\["cid-(\d+)"]=(.*);', integration_script)
            if result is None:
                raise RegexNotFoundError("Unable to extract integration JSON")

            content_id = int(result.group(1))
            content_info = json.loads(result.group(2))
            content_info_content = json.loads(content_info["jsonContent"])

            video = {
                "_type": "video",
                "id": str(content_id),
                "title": content_info["title"],
                "chapter": content_info["title"],
                "formats": [
                    {
                        "url": "https://www.studon.fau.de/studon/data/StudOn/h5p/content/" + str(content_id) + "/" +
                               f["path"],
                        "format_id": f["mime"]
                    }
                    for f in content_info_content["interactiveVideo"]["video"]["files"]
                ]
            }
            if prepend:
                collected_videos.insert(0, video)
            else:
                collected_videos.append(video)

            nonlocal grand_title
            grand_title_tag = self._search_regex("(<h1.*/h1>)", webpage, "grand_title_tag")
            grand_title = clean_html(grand_title_tag).strip()

            return (
                self._switch_page_link(contents_id, prev=True) in webpage,
                self._switch_page_link(contents_id, prev=False) in webpage
            )

        (first_prev, first_next) = fetch_one(prepend=False)
        if first_prev:
            # go to first page, collecting the videos on the way
            num_pressed_prev = 0
            while True:
                self._switch_page(contents_id, prev=True)
                num_pressed_prev += 1
                if not fetch_one(prepend=True)[0]:
                    break
            # go back to original page if we have to
            if first_next:
                for i in range(num_pressed_prev):
                    self._switch_page(contents_id, prev=False)
        if first_next:
            # go to last page, collecting videos on the way
            while True:
                self._switch_page(contents_id, prev=False)
                if not fetch_one(prepend=False)[1]:
                    break

        for i, v in enumerate(collected_videos):
            v["chapter_number"] = i + 1

        playlist = {
            "_type": "multi_video",
            "id": contents_id,
            "title": grand_title,
            "entries": collected_videos,
        }

        return playlist


class FauStudonFolderIE(InfoExtractor):
    _URL_FILE = r'ilias\.php\?ref_id=(?P<id>\d+)(&type=\w+)?(&expand=(?P<expand>-?\d+))?&cmd=view&cmdClass=ilobjfoldergui&cmdNode=yn:ou&baseClass=ilrepositorygui(#.*)?'
    _VALID_URL = r'https://www\.studon\.fau\.de/studon/' + _URL_FILE

    def _real_extract(self, url):
        folder_id = self._match_id(url)
        webpage = self._download_webpage(url, folder_id)

        # expand all
        for expander in re.finditer(self._URL_FILE.replace('&', '&amp;'), webpage):
            expand_group = expander.group("expand")
            if expand_group is not None and expand_group[0] != '-':
                webpage = self._download_webpage(
                    "https://www.studon.fau.de/studon/" + expander.group().replace('&amp;', '&'), folder_id)

        videos = []
        for item in re.finditer(
                r'<a href="(ilias\.php\?baseClass=ilObjPluginDispatchGUI&amp;cmd=forward&amp;ref_id=(\d+)&amp;forwardCmd=showContents)" target=\'_top\'><img alt="Symbol H5P"',
                webpage):
            videos.append({
                "_type": "url",
                "id": item.group(2),
                "url": "https://www.studon.fau.de/studon/" + item.group(1).replace('&amp;', '&')
            })

        grand_title_tag = self._search_regex("(<h1.*/h1>)", webpage, "grand_title_tag")
        grand_title = clean_html(grand_title_tag).strip()

        return {
            "_type": "playlist",
            "title": grand_title,
            "entries": videos
        }

