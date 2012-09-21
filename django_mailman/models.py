# -*- coding: utf-8 -*-
import re
import os
import sys
import time
from datetime import datetime
import urllib2
from cStringIO import StringIO
from types import UnicodeType
from copy import deepcopy
from email.utils import parseaddr, parsedate
import gzip
import mailbox
import tempfile

from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import utc

from webcall import MultipartPostHandler

# Mailman-Messages for a successful list creation
CREATELIST_MSG = (
    u'successfully created', # en
)

# Mailman-Messages for a successfull subscription
SUBSCRIBE_MSG = (
    u'Erfolgreich eingetragen', # de
    u'Successfully subscribed', # en
    u'Abonnement r\xe9ussi', # fr
)

# Mailman-Messages for successfully remove from a list
UNSUBSCRIBE_MSG = (
    u'Erfolgreich beendete Abonnements', # de
    u'Successfully Removed', # en
    u'Successfully Unsubscribed', # also en
    u'R\xe9siliation r\xe9ussie', # fr
)

# Mailman-Messages for a failed remove from a list
NON_MEMBER_MSG = (
    u'Nichtmitglieder können nicht aus der Mailingliste ausgetragen werden', # de
    u'Cannot unsubscribe non-members', # en
    u"Ne peut r\xe9silier l'abonnement de non-abonn\xe9s ", # fr
)

# To control user form unsubscription
UNSUBSCRIBE_BUTTON = {
    'fr' : 'Résilier',
}

# Definition from the Mailman-Source ../Mailman/Default.py
LANGUAGES = (
    ('utf-8',       _('Arabic')),
    ('utf-8',       _('Catalan')),
    ('iso-8859-2',  _('Czech')),
    ('iso-8859-1',  _('Danish')),
    ('iso-8859-1',  _('German')),
    ('us-ascii',    _('English (USA)')),
    ('iso-8859-1',  _('Spanish (Spain)')),
    ('iso-8859-15', _('Estonian')),
    ('iso-8859-15', _('Euskara')),
    ('iso-8859-1',  _('Finnish')),
    ('iso-8859-1',  _('French')),
    ('utf-8',       _('Galician')),
    ('utf-8',       _('Hebrew')),
    ('iso-8859-2',  _('Croatian')),
    ('iso-8859-2',  _('Hungarian')),
    ('iso-8859-15', _('Interlingua')),
    ('iso-8859-1',  _('Italian')),
    ('euc-jp',      _('Japanese')),
    ('euc-kr',      _('Korean')),
    ('iso-8859-13', _('Lithuanian')),
    ('iso-8859-1',  _('Dutch')),
    ('iso-8859-1',  _('Norwegian')),
    ('iso-8859-2',  _('Polish')),
    ('iso-8859-1',  _('Portuguese')),
    ('iso-8859-1',  _('Portuguese (Brazil)')),
    ('iso-8859-2',  _('Romanian')),
    ('koi8-r',      _('Russian')),
    ('utf-8',       _('Slovak')),
    ('iso-8859-2',  _('Slovenian')),
    ('utf-8',       _('Serbian')),
    ('iso-8859-1',  _('Swedish')),
    ('iso-8859-9',  _('Turkish')),
    ('utf-8',       _('Ukrainian')),
    ('utf-8',       _('Vietnamese')),
    ('utf-8',       _('Chinese (China)')),
    ('utf-8',       _('Chinese (Taiwan)')),
)

CREATE_DATA = {
	'autogen': 0,
	'moderate': 0,
	'notify': 1,
	'doit' : 'Create List',
}

# POST-Data for a list subcription
SUBSCRIBE_DATA = {
    'subscribe_or_invite': '0',
    'send_welcome_msg_to_this_batch': '0',
    'notification_to_list_owner': '0',
    'adminpw': None,
    'subscribees_upload': None,
}

# POST-Data for a list removal
UNSUBSCRIBE_DATA = {
    'send_unsub_ack_to_this_batch': 0,
    'send_unsub_notifications_to_list_owner': 0,
    'adminpw': None,
    'unsubscribees_upload': None,
}

DEFAULT_LIST_SETTINGS = {
    'general': dict(
        admin_immed_notify="1",
        admin_member_chunksize="30",
        admin_notify_mchanges="0",
        administrivia="1",
        anonymous_list="0",
        description="",
        emergency="0",
        first_strip_reply_to="0",
        goodbye_msg="",
        host_name="", #NOTE: must be filled by list
        include_list_post_header=1,
        include_rfc2369_headers=1,
        info="",
        max_days_to_hold="0",
        max_message_size="40",
        moderator="",
        new_member_options=["ignore", "nodupes"],
        owner="", #NOTE: must be filled by list
        real_name="", # NOTE: must be filled by list.
        reply_goes_to_list="0",
        reply_to_address="",
        respond_to_post_requests="1",
        send_goodbye_msg="0",
        send_reminders="0",
        send_welcome_msg="0",
        subject_prefix="", # NOTE: must be filled by list.
        submit="Submit Your Changes",
        umbrella_list="0",
        umbrella_member_suffix="-owner",
        welcome_msg="",
    ),
    'nondigest': dict(
        nondigestable="1",
        msg_header="",
        msg_footer= """_______________________________________________
%(real_name)s mailing list
%(real_name)s@%(host_name)s
%(web_page_url)slistinfo%(cgiext)s/%(_internal_name)s""",
        scrub_nondigest="0",
        regular_exclude_lists="",
        regular_include_lists="",
    ),
    'digest': dict(
        digestable="1",
        digest_is_default="0", # 0: Regular, 1: Digest
        mime_is_default_digest="0", # 0: Plain, 1: MIME
        digest_size_threshold="30", #kb
        digest_send_periodic="1",
        digest_header="",
        digest_footer="""_______________________________________________
%(real_name)s mailing list
%(real_name)s@%(host_name)s
%(web_page_url)slistinfo%(cgiext)s/%(_internal_name)s""",
        digest_volume_frequency="1", # 0: yearly, 1: monthly, 2: quarterly, 3: weekly, 4: daily
    ),
    'privacy/subscribing': dict(
        advertised="1",
        subscribe_policy="0",
        unsubscribe_policy="0",
        ban_list="",
        private_roster="1",
        obscure_addresses="1",
    ),
    'privacy/sender': dict(
        default_member_moderation="0",
        member_moderation_action="0",
        member_moderation_notice="",
        accept_these_nonmembers="",
        hold_these_nonmembers="",
        reject_these_nonmembers="",
        discard_these_nonmembers="",
        generic_nonmember_action="2",
        forward_auto_discards="1",
        nonmember_rejection_notice="",
    ),
    'privacy/recipient': dict(
        require_explicit_destination="1",
        acceptable_aliases="",
        max_num_recipients="10",
    ),
    'privacy/spam': dict(
        bounce_matching_headers="""# Lines that *start* with a '#' are comments.
to: friend@public.com
message-id: relay.comanche.denmark.eu
from: list@listme.com
from: .*@uplinkpro.com""",
        hdrfilter_action_01="0",
        hdrfilter_new_01="",
        hdrfilter_rebox_01="",
    ),
    'bounce': dict(
        bounce_processing="1",
        bounce_score_threshold="5.0",
        bounce_info_stale_after="7",
        bounce_you_are_disabled_warnings="3",
        bounce_you_are_disabled_warnings_interval="7",
        bounce_unrecognized_goes_to_list_owner="1",
        bounce_notify_owner_on_disable="1",
        bounce_notify_owner_on_removal="1",
    ),
    "archive": dict(
        archive="1",
        archive_private="0",
        archive_volume_frequency="1",
    ),
    "gateway": dict(
        nntp_host="",
        linked_newsgroup="",
        gateway_to_news="0",
        gateway_to_mail="0",
        news_moderation="0",
        news_prefix_subject_too="1",
    ),
    "autoreply": dict(
        autorespond_postings="0",
        autoresponse_postings_text="",
        autorespond_admin="0",
        autoresponse_admin_text="",
        autorespond_requests="0",
        autoresponse_request_text="",
        autoresponse_graceperiod="90",
    ),
    "contentfilter": dict(
        filter_content="0",
        filter_mime_types="",
        pass_mime_types="""multipart/mixed
multipart/alternative
text/plain""",
        filter_filename_extensions="""exe
bat
cmd
com
pif
scr
vbs
cpl""",
        pass_filename_extensions="",
        collapse_alternatives="1",
        convert_html_to_plaintext="1",
        filter_action="0",
    ),
    "topics": dict(
        topics_enabled="0",
        topics_bodylines_limit="5",
        topic_box_01="",
        topic_desc_01="",
        topic_new_01="",
        topic_rebox_01="",
    )
}

def check_encoding(value, encoding):
    if isinstance(value, UnicodeType) and encoding != 'utf-8':
        value = value.encode(encoding)
    if not isinstance(value, UnicodeType) and encoding == 'utf-8':
        value = unicode(value, errors='replace')
    return value


class List(models.Model):
    name = models.CharField(max_length=50, unique=True,
        help_text="The real name of the list (the part before the @) with any desired case changes.")
    password = models.CharField(max_length=50,
        help_text="The list owner's password.")
    email = models.EmailField(unique=True,
        help_text="The full email address for this list, e.g. mylist@lists.example.com")
    owner = models.TextField(
        help_text="One or more email addresses of list owners, separated by \n."
    )
    main_url = models.URLField(verify_exists=False,
        help_text="The URL to the mailman installation, e.g. http://lists.example.com/mailman/"
    )
    encoding = models.CharField(max_length=20, choices=LANGUAGES)

    class Meta:
        verbose_name = 'List-Installation'
        verbose_name_plural = 'List-Installations'

    def __unicode__(self):
        return u'%s' % (self.name)

    def __parse_status_content(self, content):
        if not content:
            raise Exception('No valid Content!')

        m = re.search('(?<=<h5>).+(?=:[ ]{0,1}</h5>)', content)
        if m:
            msg = m.group(0).rstrip()
        else:
            m = re.search('(?<=<h3><strong><font color="#ff0000" size="\+2">)'+
                          '.+(?=:[ ]{0,1}</font></strong></h3>)', content)
            if m:
                msg = m.group(0)
            else:
                raise Exception('Could not find status message')

        m = re.search('(?<=<ul>\n<li>).+(?=\n</ul>\n)', content)
        if m:
            member = m.group(0)
        else:
            raise Exception('Could not find member-information')

        msg = msg.encode(self.encoding)
        member = member.encode(self.encoding)
        return (msg, member)

    def __parse_member_content(self, content, encoding='iso-8859-1'):
        if not content:
            raise Exception('No valid Content!')
        members = []
        letters = re.findall('letter=\w{1}', content)
        chunks = re.findall('chunk=\d+', content)
        input = re.findall(
                'name=".+_realname" type="TEXT" value=".*" size="[0-9]+" >',
                content)
        for member in input:
            info = member.split('" ')
            email = re.search('(?<=name=").+(?=_realname)', info[0]).group(0)
            realname = re.search('(?<=value=").*', info[2]).group(0)
            email = unicode(email, encoding)
            realname = unicode(realname, encoding)
            members.append([realname, email])
        letters = set(letters)
        return (letters, members, chunks)

    def get_admin_moderation_url(self):
        return '%s/admindb/%s/?adminpw=%s' % (self.main_url, self.name,
                                              self.password)

    def subscribe(self, email, first_name=u'', last_name=u'', send_welcome_msg=False):
        from email.Utils import formataddr

        url = '%s/admin/%s/members/add' % (self.main_url, self.name)

        first_name = check_encoding(first_name, self.encoding)
        last_name = check_encoding(last_name, self.encoding)
        email = check_encoding(email, self.encoding)
        name = '%s %s' % (first_name, last_name)

        SUBSCRIBE_DATA['adminpw'] = self.password
        SUBSCRIBE_DATA['send_welcome_msg_to_this_batch'] = send_welcome_msg and "1" or "0"
        SUBSCRIBE_DATA['subscribees_upload'] = formataddr([name.strip(), email])
        opener = urllib2.build_opener(MultipartPostHandler(self.encoding, True))
        content = opener.open(url, SUBSCRIBE_DATA).read()

        (msg, member) = self.__parse_status_content(unicode(content, self.encoding))
        if (msg not in SUBSCRIBE_MSG):
            error = u'%s: %s' % (unicode(msg, encoding=self.encoding),
                                 unicode(member, encoding=self.encoding))
            raise Exception(error.encode(self.encoding))

    def unsubscribe(self, email):
        url = '%s/admin/%s/members/remove' % (self.main_url, self.name)

        email = check_encoding(email, self.encoding)
        UNSUBSCRIBE_DATA['adminpw'] = self.password
        UNSUBSCRIBE_DATA['unsubscribees_upload'] = email
        opener = urllib2.build_opener(MultipartPostHandler(self.encoding))
        content = opener.open(url, UNSUBSCRIBE_DATA).read()

        (msg, member) = self.__parse_status_content(content)
        if (msg not in UNSUBSCRIBE_MSG) and (msg not in NON_MEMBER_MSG):
            error = u'%s: %s' % (msg, member)
            raise Exception(error.encode(self.encoding))

    def get_all_members(self):
        url = '%s/admin/%s/members/list' % (self.main_url, self.name)
        data = { 'adminpw': self.password }
        opener = urllib2.build_opener(MultipartPostHandler(self.encoding))

        all_members = []
        content = opener.open(url, data).read()
        (letters, members, chunks) = self.__parse_member_content(content, self.encoding)
        all_members.extend(members)
        for letter in letters:
            url_letter = u"%s?%s" %(url, letter)
            content = opener.open(url_letter, data).read()
            (letters, members, chunks) = self.__parse_member_content(content, self.encoding)
            all_members.extend(members)
            for chunk in chunks[1:]:
                url_letter_chunk = "%s?%s&%s" %(url, letter, chunk)
                content = opener.open(url_letter_chunk, data).read()
                (letters, members, chunks) = self.__parse_member_content(
                        content, self.encoding)
                all_members.extend(members)

        members = {}
        for m in all_members:
            email = m[1].replace(u"%40", u"@")
            members[email] = m[0]
        all_members = [(email, name) for email, name in members.items()]
        all_members.sort()
        return all_members

    def user_subscribe(self, email, password, language='fr', first_name=u'', last_name=u''):

        url = '%s/subscribe/%s' % (self.main_url, self.name)

        password = check_encoding(password, self.encoding)
        email = check_encoding(email, self.encoding)
        first_name = check_encoding(first_name, self.encoding)
        last_name = check_encoding(last_name, self.encoding)
        name = '%s %s' % (first_name, last_name)

        SUBSCRIBE_DATA['email'] = email
        SUBSCRIBE_DATA['pw'] = password
        SUBSCRIBE_DATA['pw-conf'] = password
        SUBSCRIBE_DATA['fullname'] = name
        SUBSCRIBE_DATA['language'] = language
        opener = urllib2.build_opener(MultipartPostHandler(self.encoding, True))
        request = opener.open(url, SUBSCRIBE_DATA)
        content = request.read()
        for status in SUBSCRIBE_MSG:
            if len(re.findall(status, content)) > 0:
                return True
        raise Exception(content)

    def user_subscribe(self, email, password, language='fr', first_name=u'', last_name=u''):

        url = '%s/subscribe/%s' % (self.main_url, self.name)

        password = check_encoding(password, self.encoding)
        email = check_encoding(email, self.encoding)
        first_name = check_encoding(first_name, self.encoding)
        last_name = check_encoding(last_name, self.encoding)
        name = '%s %s' % (first_name, last_name)

        SUBSCRIBE_DATA['email'] = email
        SUBSCRIBE_DATA['pw'] = password
        SUBSCRIBE_DATA['pw-conf'] = password
        SUBSCRIBE_DATA['fullname'] = name
        SUBSCRIBE_DATA['language'] = language
        opener = urllib2.build_opener(MultipartPostHandler(self.encoding, True))
        request = opener.open(url, SUBSCRIBE_DATA)
        content = request.read()
        # no error code to process

    def user_unsubscribe(self, email, language='fr'):

        url = '%s/options/%s/%s' % (self.main_url, self.name, email)

        email = check_encoding(email, self.encoding)

        UNSUBSCRIBE_DATA['email'] = email
        UNSUBSCRIBE_DATA['language'] = language
        UNSUBSCRIBE_DATA['login-unsub'] = UNSUBSCRIBE_BUTTON[language]
        
        opener = urllib2.build_opener(MultipartPostHandler(self.encoding, True))
        request = opener.open(url, UNSUBSCRIBE_DATA)
        content = request.read()
        # no error code to process

    @classmethod
    def create_list(cls, main_url, email_domain, admin_pass, owner_email,
                    owner_password, language='en', listname=u'',
                    list_encoding='iso-8859-1'):

        url = '%s/create' % (main_url)

        owner_password = check_encoding(owner_password, list_encoding)
        owner_email = check_encoding(owner_email, list_encoding)
        listname = check_encoding(listname, list_encoding)

        CREATE_DATA['listname'] = listname
        CREATE_DATA['owner'] = owner_email
        CREATE_DATA['auth'] = admin_pass
        CREATE_DATA['password'] = owner_password
        CREATE_DATA['confirm'] = owner_password
        CREATE_DATA['langs'] = language

        opener = urllib2.build_opener(MultipartPostHandler(list_encoding, True))
        request = opener.open(url, CREATE_DATA)
        content = request.read()
        for status in CREATELIST_MSG:
            if len(re.findall(status, content)) > 0:
                list_email = '%s@%s' % (listname, email_domain)
                return cls(name=listname, password=owner_password, email=list_email, 
                           main_url=main_url, owner=owner_email, encoding=list_encoding)
        raise Exception(content)
	
    def change_settings(self, user_settings):
        new_settings = deepcopy(DEFAULT_LIST_SETTINGS)
        new_settings['general']['real_name'] = self.name
        new_settings['general']['subject_prefix'] = "[%s]" % self.name
        new_settings['general']['host_name'] = parseaddr(self.email)[1].split("@")[1]
        new_settings['general']['owner'] = self.owner

        for key in user_settings:
            new_settings[key].update(user_settings[key])

        opener = urllib2.build_opener(MultipartPostHandler(self.encoding, True))
        for key in user_settings:
            if key not in DEFAULT_LIST_SETTINGS:
                raise Exception("Unknown settings key: '%s'" % key)

            url = '%s/admin/%s/%s' % (self.main_url, self.name, key)
            post_data = {'adminpw': self.password} 
            post_data.update(new_settings[key])
            request = opener.open(url, post_data)
            # TODO: try to identify error codes, and raise an exception if one
            # is found.  The usual case is that nothing is returned.  Another
            # strategy would be to parse the page form, and ensure its values
            # match the posted ones.

class ListMessageManager(models.Manager):
    def create_from_archive(self, mlist, month_dt, is_private=True):
        filename = month_dt.strftime("%Y-%B").title() + ".txt.gz"
        if is_private:
            url = '%s/private/%s/%s' % (mlist.main_url, mlist.name, filename)
            opener = urllib2.build_opener(MultipartPostHandler(mlist.encoding, True))
            try:
                request = opener.open(url, {
                    'username': '',
                    'password': mlist.password,
                })
            except urllib2.HTTPError:
                return None
            content = request
        else:
            url = '%s/../pipermail/%s/%s' % (mlist.main_url, mlist.name, filename)
            try:
                request = urllib2.urlopen(url)
            except urllib2.HTTPError:
                return None
            content = request

        # Python's mailbox.mbox requires a real, named file path.
        name = None
        with tempfile.NamedTemporaryFile(delete=False) as fh:
            txt = request.read()
            print txt
            fh.write(txt)
            name = fh.name
        mbox = mailbox.mbox(name)

        msgs = []
        for msg in mbox:
            listmessage, created = ListMessage.objects.get_or_create(
                list=mlist,
                date=datetime.fromtimestamp(time.mktime(parsedate(msg['Date']))).replace(tzinfo=utc),
                sender=parseaddr(msg['From'].replace(" at ", "@")[1]),
                subject=msg['Subject'],
                message_id=msg.get('Message-ID', ''),
                in_reply_to=msg.get('In-Reply-To', ''),
                references=msg.get('References', ''),
                body=get_email_payload_as_string(msg),
            )
            msgs.append(listmessage)
        os.remove(name)
        return msgs

def get_email_payload_as_string(msg):
    if msg.is_multipart():
        return "\n\n".join(
            string for string in get_payload_as_string(msg.get_payload())
        )
    return msg.get_payload(decode=True)

class ListMessage(models.Model):
    list = models.ForeignKey(List)
    sender = models.EmailField()
    date = models.DateTimeField()
    subject = models.CharField(max_length=255, blank=True)
    message_id = models.CharField(max_length=255, blank=True)
    in_reply_to = models.CharField(max_length=255, blank=True)
    references = models.CharField(max_length=255, blank=True)
    body = models.TextField()

    objects = ListMessageManager()

    def __unicode__(self):
        return self.message_id
