"""
測試功能模組
提供基礎的字符串與數學工具函數
"""


def reverse_string(text: str) -> str:
    """反轉字符串"""
    return text[::-1]


def is_even(number: int) -> bool:
    """判斷是否為偶數"""
    return number % 2 == 0


def safe_divide(a: float, b: float) -> float:
    """安全除法，除數為零時拋出異常"""
    if b == 0:
        raise ValueError("除數不可為零")
    return a / b
