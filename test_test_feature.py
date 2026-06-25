"""
測試功能模組的單元測試
使用 Python 標準庫 unittest
"""

import unittest
from test_feature import reverse_string, is_even, safe_divide


class TestStringOperations(unittest.TestCase):
    def test_reverse_string_normal(self):
        self.assertEqual(reverse_string("hello"), "olleh")

    def test_reverse_string_empty(self):
        self.assertEqual(reverse_string(""), "")

    def test_reverse_string_palindrome(self):
        self.assertEqual(reverse_string("racecar"), "racecar")


class TestMathOperations(unittest.TestCase):
    def test_is_even_true(self):
        self.assertTrue(is_even(4))

    def test_is_even_false(self):
        self.assertFalse(is_even(3))

    def test_safe_divide_success(self):
        self.assertAlmostEqual(safe_divide(10, 2), 5.0)

    def test_safe_divide_by_zero(self):
        with self.assertRaises(ValueError) as context:
            safe_divide(10, 0)
        self.assertEqual(str(context.exception), "除數不可為零")


if __name__ == "__main__":
    unittest.main()
