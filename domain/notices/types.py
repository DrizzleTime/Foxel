from pydantic import BaseModel


class NoticeItem(BaseModel):
    id: int
    title: str
    contentMd: str
    isPopup: bool
    createdAt: int


class NoticeListResponse(BaseModel):
    items: list[NoticeItem]
    page: int
    pageSize: int
    total: int
