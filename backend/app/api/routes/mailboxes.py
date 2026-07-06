from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.mailbox import (
    MailboxCreate,
    MailboxResponse,
    MailboxTestConnectionResponse,
    MailboxUpdate,
)
from app.services.mailbox_service import MailboxService

router = APIRouter(prefix="/api/mailboxes", tags=["mailboxes"])


def _get_or_404(service: MailboxService, mailbox_id: int):
    mailbox = service.get(mailbox_id)
    if mailbox is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox not found.")
    return mailbox


@router.get("", response_model=list[MailboxResponse])
def list_mailboxes(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return MailboxService(db).list_mailboxes()


@router.post("", response_model=MailboxResponse, status_code=status.HTTP_201_CREATED)
def create_mailbox(
    payload: MailboxCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    service = MailboxService(db)
    data = payload.model_dump(exclude={"imap_password"})
    return service.create(imap_password=payload.imap_password, **data)


@router.get("/{mailbox_id}", response_model=MailboxResponse)
def get_mailbox(mailbox_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _get_or_404(MailboxService(db), mailbox_id)


@router.put("/{mailbox_id}", response_model=MailboxResponse)
def update_mailbox(
    mailbox_id: int,
    payload: MailboxUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    service = MailboxService(db)
    mailbox = _get_or_404(service, mailbox_id)
    data = payload.model_dump(exclude={"imap_password"}, exclude_unset=True)
    return service.update(mailbox, imap_password=payload.imap_password, **data)


@router.delete("/{mailbox_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mailbox(mailbox_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    service = MailboxService(db)
    mailbox = _get_or_404(service, mailbox_id)
    service.delete(mailbox)


@router.post("/{mailbox_id}/activate", response_model=MailboxResponse)
def activate_mailbox(mailbox_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    service = MailboxService(db)
    mailbox = _get_or_404(service, mailbox_id)
    return service.set_active(mailbox, True)


@router.post("/{mailbox_id}/deactivate", response_model=MailboxResponse)
def deactivate_mailbox(mailbox_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    service = MailboxService(db)
    mailbox = _get_or_404(service, mailbox_id)
    return service.set_active(mailbox, False)


@router.post("/{mailbox_id}/test-connection", response_model=MailboxTestConnectionResponse)
def test_mailbox_connection(
    mailbox_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    service = MailboxService(db)
    mailbox = _get_or_404(service, mailbox_id)
    success, message = service.test_connection(mailbox)
    return MailboxTestConnectionResponse(success=success, message=message)
