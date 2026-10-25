# -*- coding: utf-8 -*-
"""天气定位修复测试（2026-10-25：重庆长沙镇截胡案）。

全 mock 零真网（纪律：不再频繁请求 API）：_pick_geo_candidate 过滤链 +
weather_now 三态（经纬度直用/正确候选/兜底坐标）+ 旧引擎同修。
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import search_tools

# 真实事故样本（2026-10-25 geocoding 实抓：前五无湖南长沙）
GEO_SAMPLES = [
    {"name": "长沙", "admin1": "重庆市", "country_code": "CN",
     "latitude": 31.0, "longitude": 108.30, "population": 47170},
    {"name": "长沙", "admin1": "贵州", "country_code": "CN",
     "latitude": 28.69, "longitude": 105.99, "population": 1653},
    {"name": "长沙", "admin1": "广东", "country_code": "CN",
     "latitude": 24.22, "longitude": 116.12, "population": None},
    {"name": "Changsha", "admin1": "Hunan", "country_code": "CN",
     "latitude": 28.23, "longitude": 112.94, "population": 7044118},
]


class PickGeoCandidateTests(unittest.TestCase):
    """过滤链核心：CN+全等+population 最大（截胡防线）。"""

    def test_hijack_chain_blocked_by_fallback_table(self):
        """截胡链终结（真实事故）：搜"长沙"不再走 geocoding（中文全等命中的
        是重庆长沙镇，湖南条目是英文 Changsha 不同名，pop 过滤挡不住）——
        表内城市前置直用兜底坐标，weather_now 全程零 geocoding 请求。"""
        fc = MagicMock()
        fc.json.return_value = {"current_weather": {
            "temperature": 18.9, "weathercode": 3, "windspeed": 3.0}}
        with patch("agent_state.state_manager.get_user_location",
                   return_value={"city": "长沙", "district": "天心区"}),                 patch.object(search_tools.requests, "get", return_value=fc) as rg:
            d = search_tools.weather_now()
        self.assertEqual(d["city"], "长沙·天心区")
        self.assertEqual(d["temp"], 18.9)
        self.assertIn("forecast", str(rg.call_args))   # 唯一请求=天气（非 geocoding）

    def test_english_exact_match_finds_hunan(self):
        """全等语义：搜"Changsha"命中湖南（英文条目）。"""
        pick = search_tools._pick_geo_candidate(GEO_SAMPLES, "Changsha")
        self.assertEqual(pick["admin1"], "Hunan")
        self.assertAlmostEqual(pick["latitude"], 28.23, places=1)

    def test_cn_filter_blocks_foreign(self):
        """非 CN 条目一律排除（countryCode=CN 过滤）。"""
        samples = GEO_SAMPLES + [
            {"name": "长沙", "admin1": "Tokyo", "country_code": "JP",
             "latitude": 35.0, "longitude": 139.0, "population": 99999999}]
        pick = search_tools._pick_geo_candidate(samples, "长沙")
        self.assertEqual(pick["country_code"], "CN")

    def test_no_match_returns_none(self):
        self.assertIsNone(search_tools._pick_geo_candidate(GEO_SAMPLES, "武汉"))


class WeatherNowTests(unittest.TestCase):
    """weather_now 三态（mock 网络+定位链）。"""

    def _mock_loc(self, city="长沙", district="天心区", lat=None, lon=None):
        loc = {"city": city, "district": district}
        if lat is not None:
            loc["lat"], loc["lon"] = lat, lon
        return patch("agent_state.state_manager.get_user_location",
                     return_value=loc)

    def _mock_forecast(self, temp=19.1, code=2):
        m = MagicMock()
        m.json.return_value = {"current_weather": {
            "temperature": temp, "weathercode": code, "windspeed": 4.1}}
        return patch.object(search_tools.requests, "get", return_value=m)

    def test_local_coords_direct(self):
        """本地经纬度直用（不再 geocoding 瞎猜）——user_location 有 lat/lon。"""
        with self._mock_loc(lat=28.14, lon=113.03), self._mock_forecast(19.1, 2):
            d = search_tools.weather_now()
        self.assertEqual(d["temp"], 19.1)
        self.assertEqual(d["desc"], "多云")
        self.assertEqual(d["city"], "长沙·天心区")   # district 展示

    def test_outside_table_geo_dead_raises(self):
        """表外城市 geocoding 全灭 → 人话报错（不猜不静默）。"""
        geo = MagicMock()
        geo.json.return_value = {"results": []}
        with self._mock_loc(city="武汉", district="洪山区"),                 patch.object(search_tools.requests, "get", return_value=geo):
            self.assertRaises(RuntimeError, search_tools.weather_now)

    def test_outside_table_geo_picks_right_city(self):
        """表外城市走 geocoding：CN+全等+pop 最大命中正确城市（武汉样例）。"""
        geo = MagicMock()
        geo.json.return_value = {"results": [
            {"name": "武汉", "admin1": "湖北", "country_code": "CN",
             "latitude": 30.59, "longitude": 114.31, "population": 11000000},
            {"name": "武汉", "admin1": "山东", "country_code": "CN",
             "latitude": 36.0, "longitude": 118.0, "population": 5000}]}
        fc = MagicMock()
        fc.json.return_value = {"current_weather": {
            "temperature": 22.0, "weathercode": 0, "windspeed": 2.0}}
        state = {"n": 0}

        def side(url, **kw):
            state["n"] += 1
            return geo if state["n"] == 1 else fc
        with self._mock_loc(city="武汉", district="洪山区"),                 patch.object(search_tools.requests, "get", side_effect=side):
            d = search_tools.weather_now()
        self.assertEqual(d["temp"], 22.0)
        self.assertEqual(d["city"], "武汉·洪山区")

    def test_geo_correct_candidate_picked(self):
        """geocoding 命中正确候选（搜 Changsha 形态）走坐标。"""
        geo = MagicMock()
        geo.json.return_value = {"results": GEO_SAMPLES}
        fc = MagicMock()
        fc.json.return_value = {"current_weather": {
            "temperature": 18.6, "weathercode": 2, "windspeed": 5.5}}

        state = {"n": 0}

        def side(url, **kw):
            state["n"] += 1
            return geo if state["n"] == 1 else fc
        with self._mock_loc(city="Changsha", district=""), \
                patch.object(search_tools.requests, "get", side_effect=side):
            d = search_tools.weather_now()
        self.assertEqual(d["temp"], 18.6)
        self.assertEqual(d["city"], "Changsha")      # 无 district 纯城市名

    def test_no_location_raises(self):
        with patch("agent_state.state_manager.get_user_location",
                   return_value={}):
            self.assertRaises(RuntimeError, search_tools.weather_now)


class FallbackTableTests(unittest.TestCase):
    """兜底坐标表完整性（新增城市必带三元组）。"""

    def test_fallback_table_shape(self):
        for city, v in search_tools._FALLBACK_COORDS.items():
            self.assertEqual(len(v), 3, city)
            lat, lon, disp = v
            self.assertTrue(18 <= lat <= 54, city)    # 中国纬度域
            self.assertTrue(73 <= lon <= 135, city)   # 中国经度域
            self.assertTrue(disp)


if __name__ == "__main__":
    unittest.main()
