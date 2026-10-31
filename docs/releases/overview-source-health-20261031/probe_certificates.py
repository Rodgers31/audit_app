import subprocess,json,re,datetime
from cryptography import x509
from cryptography.hazmat.primitives import hashes
rows=[]
for host in ["www.knbs.or.ke","www.treasury.go.ke"]:
 try:
  r=subprocess.run(["openssl","s_client","-connect",host+":443","-servername",host,"-showcerts","-verify_return_error"],input=b"",capture_output=True,timeout=8)
  certs=[]
  for pem in re.findall(b"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",r.stdout,re.S):
   c=x509.load_pem_x509_certificate(pem);certs.append({"subject":c.subject.rfc4514_string(),"issuer":c.issuer.rfc4514_string(),"not_before":c.not_valid_before_utc.isoformat(),"not_after":c.not_valid_after_utc.isoformat(),"sha256":c.fingerprint(hashes.SHA256()).hex()})
  rows.append({"host":host,"exit":r.returncode,"served_chain":certs,"verification_diagnostics":[s for s in r.stderr.decode(errors="replace").splitlines() if "verify" in s.lower() or "depth=" in s]})
 except subprocess.TimeoutExpired:rows.append({"host":host,"error":"8-second diagnostic deadline exceeded"})
print(json.dumps({"at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"results":rows},indent=2))
