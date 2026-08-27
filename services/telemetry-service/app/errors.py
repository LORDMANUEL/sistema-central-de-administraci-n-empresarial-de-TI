from fastapi import Request
from fastapi.responses import JSONResponse
class GuardianError(RuntimeError):
 def __init__(self,status_code:int,code:str,message:str):super().__init__(message);self.status_code=status_code;self.code=code;self.message=message
async def guardian_error_handler(request:Request,exc:GuardianError):return JSONResponse(status_code=exc.status_code,content={"error":{"code":exc.code,"message":exc.message,"request_id":getattr(request.state,"request_id",None)}})
