from __future__ import annotations

from typing import Final, Literal, TypeAlias

ALL_IDENTIFIERS: Final[tuple[str, ...]] = (
    "chrome_103", "chrome_104", "chrome_105", "chrome_106", "chrome_107", "chrome_108", "chrome_109", "chrome_110", "chrome_111", "chrome_112", "chrome_116_PSK", "chrome_116_PSK_PQ", "chrome_117", "chrome_120", "chrome_124", "chrome_130_PSK", "chrome_131", "chrome_131_PSK", "chrome_133", "chrome_133_PSK", "chrome_144", "chrome_144_PSK", "chrome_146", "chrome_146_PSK", "chrome_150", "chrome_150_PSK", "chrome_152", "chrome_152_PSK", "brave_146", "brave_146_PSK", "safari_15_6_1", "safari_16_0", "safari_ipad_15_6", "safari_ios_15_5", "safari_ios_15_6", "safari_ios_16_0", "safari_ios_17_0", "safari_ios_18_0", "safari_ios_18_5", "safari_ios_26_0", "firefox_102", "firefox_104", "firefox_105", "firefox_106", "firefox_108", "firefox_110", "firefox_117", "firefox_120", "firefox_123", "firefox_132", "firefox_133", "firefox_135", "firefox_146_PSK", "firefox_147", "firefox_147_PSK", "firefox_148", "opera_89", "opera_90", "opera_91", "zalando_android_mobile", "zalando_ios_mobile", "nike_ios_mobile", "nike_android_mobile", "cloudscraper", "mms_ios", "mms_ios_1", "mms_ios_2", "mms_ios_3", "mesh_ios", "mesh_ios_1", "mesh_ios_2", "mesh_android", "mesh_android_1", "mesh_android_2", "confirmed_ios", "confirmed_android", "okhttp4_android_7", "okhttp4_android_8", "okhttp4_android_9", "okhttp4_android_10", "okhttp4_android_11", "okhttp4_android_12", "okhttp4_android_13",
)
ClientIdentifier: TypeAlias = Literal[tuple(ALL_IDENTIFIERS)]

class Profiles:
    LATEST_CHROME = "chrome_152"
    CHROME_152 = "chrome_152"
    CHROME_150 = "chrome_150"
    CHROME_144 = "chrome_144"
    FIREFOX_148 = "firefox_148"
    SAFARI_IOS_26_0 = "safari_ios_26_0"

for _name in ALL_IDENTIFIERS:
    setattr(Profiles, _name.upper(), _name)


def find(value: str) -> list[str]:
    value = value.lower()
    return [item for item in ALL_IDENTIFIERS if value in item.lower()]


def validate(value: str | None) -> str:
    if value is None or value == "":
        return Profiles.LATEST_CHROME
    if value in ALL_IDENTIFIERS:
        return value
    matches = sorted(ALL_IDENTIFIERS, key=lambda item: sum(a == b for a, b in zip(value, item)), reverse=True)[:3]
    raise ValueError(f"unknown client_identifier {value!r}; did you mean: {', '.join(matches)}")
