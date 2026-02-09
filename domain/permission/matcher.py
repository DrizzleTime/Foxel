import re
import fnmatch
from functools import lru_cache


class PathMatcher:
    """路径匹配器，支持精确匹配、通配符匹配和正则匹配"""

    @classmethod
    def normalize_path(cls, path: str) -> str:
        """规范化路径"""
        if not path:
            return "/"
        # 确保以 / 开头
        if not path.startswith("/"):
            path = "/" + path
        # 移除末尾的 /（除了根路径）
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        return path

    @classmethod
    def get_parent_path(cls, path: str) -> str | None:
        """获取父目录路径"""
        path = cls.normalize_path(path)
        if path == "/":
            return None
        parent = "/".join(path.rsplit("/", 1)[:-1])
        return parent if parent else "/"

    @classmethod
    def match_pattern(cls, path: str, pattern: str, is_regex: bool = False) -> bool:
        """
        匹配路径和模式
        
        Args:
            path: 要匹配的路径
            pattern: 匹配模式
            is_regex: 是否为正则表达式
            
        Returns:
            是否匹配
        """
        path = cls.normalize_path(path)
        pattern = cls.normalize_path(pattern)

        if is_regex:
            return cls._match_regex(path, pattern)
        else:
            return cls._match_glob(path, pattern)

    @classmethod
    def _match_regex(cls, path: str, pattern: str) -> bool:
        """正则表达式匹配"""
        try:
            # 限制正则表达式的复杂度，防止 ReDoS 攻击
            if len(pattern) > 500:
                return False
            regex = re.compile(pattern)
            return bool(regex.match(path))
        except re.error:
            return False

    @classmethod
    def _match_glob(cls, path: str, pattern: str) -> bool:
        """
        通配符匹配
        
        支持的语法：
        - * : 匹配单层目录中的任意字符
        - ** : 匹配任意层级目录
        - ? : 匹配单个字符
        """
        # 精确匹配
        if pattern == path:
            return True

        # 处理 ** 通配符
        if "**" in pattern:
            return cls._match_double_star(path, pattern)

        # 使用 fnmatch 进行标准通配符匹配
        return fnmatch.fnmatch(path, pattern)

    @classmethod
    def _match_double_star(cls, path: str, pattern: str) -> bool:
        """处理 ** 通配符匹配"""
        # 将 ** 替换为特殊标记
        parts = pattern.split("**")

        if len(parts) == 2:
            prefix, suffix = parts
            # 移除 prefix 末尾的 / 和 suffix 开头的 /
            prefix = prefix.rstrip("/") if prefix else ""
            suffix = suffix.lstrip("/") if suffix else ""

            # 检查前缀匹配
            if prefix and not path.startswith(prefix):
                return False

            # 如果没有后缀，只需要前缀匹配
            if not suffix:
                return True

            # 检查后缀匹配
            remaining = path[len(prefix):].lstrip("/") if prefix else path.lstrip("/")
            
            # 后缀可以出现在任意位置
            if "*" in suffix or "?" in suffix:
                # 后缀包含通配符，逐层检查
                path_parts = remaining.split("/")
                suffix_parts = suffix.split("/")
                
                # 简化处理：检查路径的最后几层是否与后缀匹配
                if len(path_parts) >= len(suffix_parts):
                    tail = "/".join(path_parts[-len(suffix_parts):])
                    return fnmatch.fnmatch(tail, suffix)
                return False
            else:
                # 后缀是精确字符串
                return remaining.endswith(suffix) or ("/" + suffix) in remaining or remaining == suffix

        # 多个 ** 的情况，使用简化匹配
        regex_pattern = pattern.replace("**", ".*").replace("*", "[^/]*").replace("?", ".")
        try:
            return bool(re.match(f"^{regex_pattern}$", path))
        except re.error:
            return False

    @classmethod
    def get_pattern_specificity(cls, pattern: str, is_regex: bool = False) -> int:
        """
        计算模式的具体程度（用于优先级排序）
        
        返回值越大表示模式越具体
        """
        pattern = cls.normalize_path(pattern)

        if is_regex:
            # 正则表达式具体程度较低
            return len(pattern) // 2

        # 精确路径最具体
        if "*" not in pattern and "?" not in pattern:
            return len(pattern) * 10

        # 计算非通配符部分的长度
        specificity = 0
        parts = pattern.split("/")
        for part in parts:
            if part == "**":
                specificity += 1
            elif "*" in part or "?" in part:
                specificity += 5
            else:
                specificity += 10

        return specificity
