# -*- coding: utf-8 -*-
"""
h2/settings
~~~~~~~~~~~

This module contains a HTTP/2 settings object. This object provides a simple
API for manipulating HTTP/2 settings, keeping track of both the current active
state of the settings and the unacknowledged future values of the settings.
"""
import collections

from hyperframe.frame import SettingsFrame

from h2.errors import PROTOCOL_ERROR, FLOW_CONTROL_ERROR
from h2.exceptions import InvalidSettingsValueError


# Aliases for all the settings values.

#: Allows the sender to inform the remote endpoint of the maximum size of the
#: header compression table used to decode header blocks, in octets.
HEADER_TABLE_SIZE = SettingsFrame.HEADER_TABLE_SIZE

#: This setting can be used to disable server push. To disable server push on
#: a client, set this to 0.
ENABLE_PUSH = SettingsFrame.ENABLE_PUSH

#: Indicates the maximum number of concurrent streams that the sender will
#: allow.
MAX_CONCURRENT_STREAMS = SettingsFrame.MAX_CONCURRENT_STREAMS

#: Indicates the sender's initial window size (in octets) for stream-level flow
#: control.
INITIAL_WINDOW_SIZE = SettingsFrame.INITIAL_WINDOW_SIZE

try:  # Platform-specific: Hyperframe < 4.0.0
    #: Indicates the size of the largest frame payload that the sender is
    #: willing to receive, in octets.
    MAX_FRAME_SIZE = SettingsFrame.SETTINGS_MAX_FRAME_SIZE
except AttributeError:  # Platform-specific: Hyperframe >= 4.0.0
    #: Indicates the size of the largest frame payload that the sender is
    #: willing to receive, in octets.
    MAX_FRAME_SIZE = SettingsFrame.MAX_FRAME_SIZE

try:  # Platform-specific: Hyperframe < 4.0.0
    #: This advisory setting informs a peer of the maximum size of header list
    #: that the sender is prepared to accept, in octets.  The value is based on
    #: the uncompressed size of header fields, including the length of the name
    #: and value in octets plus an overhead of 32 octets for each header field.
    #:
    #: .. versionadded:: 2.5.0
    MAX_HEADER_LIST_SIZE = SettingsFrame.SETTINGS_MAX_HEADER_LIST_SIZE
except AttributeError:  # Platform-specific: Hyperframe >= 4.0.0
    #: This advisory setting informs a peer of the maximum size of header list
    #: that the sender is prepared to accept, in octets.  The value is based on
    #: the uncompressed size of header fields, including the length of the name
    #: and value in octets plus an overhead of 32 octets for each header field.
    #:
    #: .. versionadded:: 2.5.0
    MAX_HEADER_LIST_SIZE = SettingsFrame.MAX_HEADER_LIST_SIZE


#: A value structure for storing changed settings.
ChangedSetting = collections.namedtuple(
    'ChangedSetting', ['setting', 'original_value', 'new_value']
)


class Settings(collections.MutableMapping):
    """
    An object that encapsulates HTTP/2 settings state.

    HTTP/2 Settings are a complex beast. Each party, remote and local, has its
    own settings and a view of the other party's settings. When a settings
    frame is emitted by a peer it cannot assume that the new settings values
    are in place until the remote peer acknowledges the setting. In principle,
    multiple settings changes can be "in flight" at the same time, all with
    different values.

    This object encapsulates this mess. It provides a dict-like interface to
    settings, which return the *current* values of the settings in question.
    Additionally, it keeps track of the stack of proposed values: each time an
    acknowledgement is sent/received, it updates the current values with the
    stack of proposed values. On top of all that, it validates the values to
    make sure they're allowed, and raises :class:`InvalidSettingsValueError
    <h2.exceptions.InvalidSettingsValueError>` if they are not.

    Finally, this object understands what the default values of the HTTP/2
    settings are, and sets those defaults appropriately.

    .. versionchanged:: 2.2.0
       Added the ``initial_values`` parameter.

    .. versionchanged:: 2.5.0
       Added the ``max_header_list_size`` property.

    :param client: (optional) Whether these settings should be defaulted for a
        client implementation or a server implementation. Defaults to ``True``.
    :type client: ``bool``
    :param initial_values: (optional) Any initial values the user would like
        set, rather than RFC 7540's defaults.
    :type initial_vales: ``MutableMapping``
    """
    def __init__(self, client=True, initial_values=None):
        # Backing object for the settings. This is a dictionary of
        # (setting: [list of values]), where the first value in the list is the
        # current value of the setting. Strictly this doesn't use lists but
        # instead uses collections.deque to avoid repeated memory allocations.
        #
        # This contains the default values for HTTP/2.
        self._settings = {
            HEADER_TABLE_SIZE: collections.deque([4096]),
            ENABLE_PUSH: collections.deque([int(client)]),
            INITIAL_WINDOW_SIZE: collections.deque([65535]),
            MAX_FRAME_SIZE: collections.deque([16384]),
        }
        if initial_values is not None:
            for key, value in initial_values.items():
                invalid = _validate_setting(key, value)
                if invalid:
                    raise InvalidSettingsValueError(
                        "Setting %d has invalid value %d" % (key, value),
                        error_code=invalid
                    )
                self._settings[key] = collections.deque([value])

    def acknowledge(self):
        """
        The settings have been acknowledged, either by the user (remote
        settings) or by the remote peer (local settings).

        :returns: A dict of {setting: ChangedSetting} that were applied.
        """
        changed_settings = {}

        # If there is more than one setting in the list, we have a setting
        # value outstanding. Update them.
        for k, v in self._settings.items():
            if len(v) > 1:
                old_setting = v.popleft()
                new_setting = v[0]
                changed_settings[k] = ChangedSetting(
                    k, old_setting, new_setting
                )

        return changed_settings

    # Provide easy-access to well known settings.
    @property
    def header_table_size(self):
        """
        The current value of the :data:`HEADER_TABLE_SIZE
        <h2.settings.HEADER_TABLE_SIZE>` setting.
        """
        return self[HEADER_TABLE_SIZE]

    @header_table_size.setter
    def header_table_size(self, value):
        self[HEADER_TABLE_SIZE] = value

    @property
    def enable_push(self):
        """
        The current value of the :data:`ENABLE_PUSH <h2.settings.ENABLE_PUSH>`
        setting.
        """
        return self[ENABLE_PUSH]

    @enable_push.setter
    def enable_push(self, value):
        self[ENABLE_PUSH] = value

    @property
    def initial_window_size(self):
        """
        The current value of the :data:`INITIAL_WINDOW_SIZE
        <h2.settings.INITIAL_WINDOW_SIZE>` setting.
        """
        return self[INITIAL_WINDOW_SIZE]

    @initial_window_size.setter
    def initial_window_size(self, value):
        self[INITIAL_WINDOW_SIZE] = value

    @property
    def max_frame_size(self):
        """
        The current value of the :data:`MAX_FRAME_SIZE
        <h2.settings.MAX_FRAME_SIZE>` setting.
        """
        return self[MAX_FRAME_SIZE]

    @max_frame_size.setter
    def max_frame_size(self, value):
        self[MAX_FRAME_SIZE] = value

    @property
    def max_concurrent_streams(self):
        """
        The current value of the :data:`MAX_CONCURRENT_STREAMS
        <h2.settings.MAX_CONCURRENT_STREAMS>` setting.
        """
        return self.get(MAX_CONCURRENT_STREAMS, 2**32+1)

    @max_concurrent_streams.setter
    def max_concurrent_streams(self, value):
        self[MAX_CONCURRENT_STREAMS] = value

    @property
    def max_header_list_size(self):
        """
        The current value of the :data:`MAX_HEADER_LIST_SIZE
        <h2.settings.MAX_HEADER_LIST_SIZE>` setting. If not set, returns
        ``None``, which means unlimited.

        .. versionadded:: 2.5.0
        """
        return self.get(MAX_HEADER_LIST_SIZE, None)

    @max_header_list_size.setter
    def max_header_list_size(self, value):
        self[MAX_HEADER_LIST_SIZE] = value

    # Implement the MutableMapping API.
    def __getitem__(self, key):
        val = self._settings[key][0]

        # Things that were created when a setting was received should stay
        # KeyError'd.
        if val is None:
            raise KeyError

        return val

    def __setitem__(self, key, value):
        invalid = _validate_setting(key, value)
        if invalid:
            raise InvalidSettingsValueError(
                "Setting %d has invalid value %d" % (key, value),
                error_code=invalid
            )

        try:
            items = self._settings[key]
        except KeyError:
            items = collections.deque([None])
            self._settings[key] = items

        items.append(value)

    def __delitem__(self, key):
        del self._settings[key]

    def __iter__(self):
        return self._settings.__iter__()

    def __len__(self):
        return len(self._settings)


def _validate_setting(setting, value):
    """
    Confirms that a specific setting has a well-formed value. If the setting is
    invalid, returns an error code. Otherwise, returns 0 (NO_ERROR).
    """
    if setting == ENABLE_PUSH:
        if value not in (0, 1):
            return PROTOCOL_ERROR
    elif setting == INITIAL_WINDOW_SIZE:
        if not 0 <= value <= 2147483647:  # 2^31 - 1
            return FLOW_CONTROL_ERROR
    elif setting == MAX_FRAME_SIZE:
        if not 16384 <= value <= 16777215:  # 2^14 and 2^24 - 1
            return PROTOCOL_ERROR
    elif setting == MAX_HEADER_LIST_SIZE:
        if not value > 0:
            return PROTOCOL_ERROR

    return 0
