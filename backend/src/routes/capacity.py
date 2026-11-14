from fastapi import APIRouter, Depends, Query
from src.config.database import get_db
from src.middlewares.auth import current_user, admin_only
from src.schemas.capacity import CapacityInput
from src.services import ledger
router=APIRouter(prefix='/capacity')
@router.get('')
def listing(from_:str|None=Query(None,alias='from'),to:str|None=None,db=Depends(get_db),u=Depends(current_user)):
    return ledger.ledger(db,from_,to)
@router.put('')
def update(data:CapacityInput,db=Depends(get_db),u=Depends(admin_only)):
    days=ledger.set_capacity(db,u.email,data.date_from,data.date_to,data.capacity)
    return {'updated':len(days),'from':days[0],'to':days[-1],'capacity':data.capacity}
