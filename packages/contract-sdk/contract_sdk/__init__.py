"""契约 SDK：由 contracts/ 生成的线上报文类型（HTTP DTO + 事件信封）。

演进规则（见 contracts/README.md）：
- 本包内容必须与 contracts/ 保持一致；
- CI 中通过 datamodel-code-generator 从 contracts/ 自动生成；
- 新增字段必须带默认值；禁止删除/改名已有字段。
"""

__version__ = "0.1.0"