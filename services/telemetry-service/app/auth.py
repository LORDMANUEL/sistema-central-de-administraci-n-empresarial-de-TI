from dataclasses import dataclass
from time import monotonic
import httpx,jwt
from fastapi import Depends,Request
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from jwt import ExpiredSignatureError,InvalidTokenError
from .errors import GuardianError
_b=HTTPBearer(auto_error=False)
@dataclass(frozen=True)
class IdentityPrincipal:user_id:str;role:str;bearer_token:str
class AccessTokenVerifier:
 def __init__(self,s):self.s=s;self.cache=None;self.at=0.0
 def jwks(self,force=False):
  if not force and self.cache is not None and monotonic()-self.at<300:return self.cache
  try:r=httpx.get(self.s.identity_jwks_url,timeout=5);r.raise_for_status();self.cache=r.json();self.at=monotonic();return self.cache
  except Exception as exc:raise GuardianError(503,"telemetry.identity_unavailable","Identity unavailable") from exc
 def verify(self,t):
  try:
   kid=jwt.get_unverified_header(t).get("kid");key=None
   for f in (False,True):
    for item in self.jwks(f).get("keys",[]):
     if item.get("kid")==kid:key=jwt.PyJWK.from_dict(item).key;break
    if key is not None:break
   if key is None:raise GuardianError(401,"telemetry.unknown_signing_key","Unknown signing key")
   c=jwt.decode(t,key,algorithms=["EdDSA"],issuer=self.s.identity_issuer,audience=self.s.identity_audience,options={"require":["sub","role","type","iss","aud","iat","exp","jti"]})
  except GuardianError:raise
  except ExpiredSignatureError as exc:raise GuardianError(401,"telemetry.token_expired","Access token expired") from exc
  except (InvalidTokenError,ValueError) as exc:raise GuardianError(401,"telemetry.invalid_token","Invalid access token") from exc
  if c.get("type")!="access":raise GuardianError(401,"telemetry.invalid_token_type","Access token required")
  return IdentityPrincipal(str(c["sub"]),str(c["role"]),t)
def current_principal(request:Request,credentials:HTTPAuthorizationCredentials|None=Depends(_b)):
 if credentials is None:raise GuardianError(401,"telemetry.authentication_required","Authentication required")
 return request.app.state.auth.verify(credentials.credentials)
