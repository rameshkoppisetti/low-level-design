from __future__ import annotations

import random
import threading
from enum import Enum
from typing import Dict, List, Optional


class Song:
    def __init__(self, song_id: str, title: str, artist: str, duration_seconds: int):
        self.id = song_id
        self.title = title
        self.artist = artist
        self.duration_seconds = duration_seconds

    def __repr__(self) -> str:
        return f"{self.title} - {self.artist}"


class PlaylistNode:
    def __init__(self, song: Song):
        self.song = song
        self.prev: Optional[PlaylistNode] = None
        self.next: Optional[PlaylistNode] = None


class RepeatMode(Enum):
    NONE = "NONE"
    ONE = "ONE"
    ALL = "ALL"


class ShuffleMode(Enum):
    OFF = "OFF"
    SHUFFLE = "SHUFFLE"


class PlaylistManager:
    def __init__(self):
        self.head: Optional[PlaylistNode] = None
        self.tail: Optional[PlaylistNode] = None
        self.current: Optional[PlaylistNode] = None
        self.node_map: Dict[str, PlaylistNode] = {}
        self.lock = threading.RLock()

        self.repeat_mode = RepeatMode.NONE
        self.shuffle_mode = ShuffleMode.OFF
        self.shuffle_order: List[str] = []
        self.shuffle_index = -1

    def add_song(self, song: Song) -> None:
        with self.lock:
            if song.id in self.node_map:
                raise ValueError("Song already exists in playlist.")

            new_node = PlaylistNode(song)
            self.node_map[song.id] = new_node

            if not self.head:
                self.head = new_node
                self.tail = new_node
                self.current = new_node
            else:
                self.tail.next = new_node
                new_node.prev = self.tail
                self.tail = new_node

            if self.shuffle_mode == ShuffleMode.SHUFFLE:
                self._generate_shuffle_order()

    def remove_song(self, song_id: str) -> None:
        with self.lock:
            node = self.node_map.get(song_id)
            if not node:
                return

            next_current = self._get_next_node_logical() if node == self.current else self.current
            self._unlink(node)
            del self.node_map[song_id]

            if self.shuffle_mode == ShuffleMode.SHUFFLE:
                self._generate_shuffle_order()

            self.current = next_current if next_current and next_current.song.id in self.node_map else self.head

    def move_before(self, song_id_to_move: str, target_song_id: str) -> None:
        with self.lock:
            if song_id_to_move == target_song_id:
                return

            to_move = self.node_map.get(song_id_to_move)
            target = self.node_map.get(target_song_id)

            if not to_move or not target:
                raise ValueError("Song node parameters not found.")

            self._unlink(to_move)
            self._insert_before(to_move, target)

            if self.shuffle_mode == ShuffleMode.SHUFFLE:
                self._generate_shuffle_order()

    def get_currently_playing(self) -> Optional[Song]:
        with self.lock:
            return self.current.song if self.current else None

    def next(self) -> Optional[Song]:
        with self.lock:
            if not self.current:
                return None

            if self.repeat_mode == RepeatMode.ONE:
                return self.current.song

            next_node = self._get_next_node_logical()
            if not next_node:
                self.current = None
                return None

            self.current = next_node
            return self.current.song

    def prev(self) -> Optional[Song]:
        with self.lock:
            if not self.current:
                return None

            if self.repeat_mode == RepeatMode.ONE:
                return self.current.song

            prev_node = self._get_prev_node_logical()
            if not prev_node:
                self.current = None
                return None

            self.current = prev_node
            return self.current.song

    def set_repeat_mode(self, mode: RepeatMode) -> None:
        with self.lock:
            self.repeat_mode = mode

    def toggle_shuffle(self) -> None:
        with self.lock:
            if self.shuffle_mode == ShuffleMode.OFF:
                self.shuffle_mode = ShuffleMode.SHUFFLE
                self._generate_shuffle_order()
            else:
                self.shuffle_mode = ShuffleMode.OFF
                self.shuffle_order = []
                self.shuffle_index = -1

    def get_ordered_playlist(self) -> List[Song]:
        with self.lock:
            songs = []
            runner = self.head
            while runner:
                songs.append(runner.song)
                runner = runner.next
            return songs

    def _get_next_node_logical(self) -> Optional[PlaylistNode]:
        if self.shuffle_mode == ShuffleMode.SHUFFLE:
            return self._get_next_shuffle_node()

        if self.current and self.current.next:
            return self.current.next
        if self.repeat_mode == RepeatMode.ALL:
            return self.head
        return None

    def _get_prev_node_logical(self) -> Optional[PlaylistNode]:
        if self.shuffle_mode == ShuffleMode.SHUFFLE:
            return self._get_prev_shuffle_node()

        if self.current and self.current.prev:
            return self.current.prev
        if self.repeat_mode == RepeatMode.ALL:
            return self.tail
        return None

    def _get_next_shuffle_node(self) -> Optional[PlaylistNode]:
        if not self.shuffle_order:
            return None

        self.shuffle_index += 1

        if self.shuffle_index >= len(self.shuffle_order):
            if self.repeat_mode != RepeatMode.ALL:
                return None
            self.shuffle_index = 0

        return self.node_map.get(self.shuffle_order[self.shuffle_index])

    def _get_prev_shuffle_node(self) -> Optional[PlaylistNode]:
        if not self.shuffle_order:
            return None

        self.shuffle_index -= 1

        if self.shuffle_index < 0:
            if self.repeat_mode != RepeatMode.ALL:
                return None
            self.shuffle_index = len(self.shuffle_order) - 1

        return self.node_map.get(self.shuffle_order[self.shuffle_index])

    def _generate_shuffle_order(self) -> None:
        self.shuffle_order = list(self.node_map.keys())
        random.shuffle(self.shuffle_order)

        if self.current and self.current.song.id in self.shuffle_order:
            self.shuffle_index = self.shuffle_order.index(self.current.song.id)
        elif self.shuffle_order:
            self.shuffle_index = 0
        else:
            self.shuffle_index = -1

    def _unlink(self, node: PlaylistNode) -> None:
        if node.prev:
            node.prev.next = node.next
        else:
            self.head = node.next

        if node.next:
            node.next.prev = node.prev
        else:
            self.tail = node.prev

        node.prev = None
        node.next = None

    def _insert_before(self, node: PlaylistNode, target: PlaylistNode) -> None:
        prev_of_target = target.prev

        node.next = target
        node.prev = prev_of_target
        target.prev = node

        if prev_of_target:
            prev_of_target.next = node
        else:
            self.head = node


if __name__ == "__main__":
    print("=== PYTHON PLAYLIST DEMO ===")
    manager = PlaylistManager()

    manager.add_song(Song("1", "Yesterday", "Beatles", 123))
    manager.add_song(Song("2", "Time", "Pink Floyd", 401))
    manager.add_song(Song("3", "One", "U2", 276))

    print(f"Ordered playlist: {manager.get_ordered_playlist()}")
    print(f"Currently playing: {manager.get_currently_playing()}")
    print(f"Next: {manager.next()}")

    manager.set_repeat_mode(RepeatMode.ALL)
    manager.toggle_shuffle()
    print(f"Shuffle next: {manager.next()}")

    manager.move_before("3", "1")
    print(f"After move: {manager.get_ordered_playlist()}")

    manager.remove_song("2")
    print(f"After remove: {manager.get_ordered_playlist()}")
    print("=== END OF PYTHON PLAYLIST DEMO ===")
