"""HELD proposal: acquire two native pinned CI images in one owned credential config."""
import argparse,base64,hashlib,json,os,signal,stat,subprocess,time,types
from pathlib import Path
from uuid import uuid4

HELPER_SHA='92938fe95c4d29ab5b5987047f212e2c32b028746d0cb124efb7239bc47b0041'
STATE_NAME='backend-registry-state.json'
REGISTRY='docker.io'
MAX_SECONDS=240
IMAGES={
 'postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675':{
  'amd64':{'sha256:7296f210ae81031ec955dbad9a67a84fe958572a2153b8d0826a647522904dc1','sha256:d13db94ae661d517c5ed57c509a578d5ea64aae639871ba25294f4f42d83de28'},
  'arm64':{'sha256:651ddcd1c769a6d94cf4aaca9756f2abb6acd65e712f4a386a2ff4e730586d5b','sha256:413da4542e091471785b7f18f1a2258df134bc6506ab4e1e53725aa8bcfdb650'}},
 'supabase/postgres@sha256:21ab971149317ea9cd12a8126fe4ebb34def08c8972956b0958cba0924409dab':{
  'amd64':{'sha256:9ff6402f578a9b0d4f2aa31f660bd398b8e378761d61d31efda6ff9ad92408e5','sha256:5e52ca81790ae3aa1c2f8c20df41dd96404c8ab29632dddf113b881de785ee92'},
  'arm64':{'sha256:596ad2940aadd60cf5af2a0c574f1234d149e05dc57091a467970f9755cf2012','sha256:fe361a60055b8970e35f4d4a5cd9b85388b711db2ad66815d8dd9e9968b9c3dd'}},
}
def require(ok,message):
    if not ok:raise RuntimeError(message)
def source_hash():return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
def helper(deadline):
    path=Path(__file__).with_name('prepare_browser_registry_auth.py');raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==HELPER_SHA,'Reviewed credential ownership library changed')
    m=types.ModuleType('backend_owned_registry_library');m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__)
    # Preserve the reviewed Docker function's env/custody behavior; only bound its
    # subprocess budget in this private module namespace, never the global module.
    def bounded_run(*args,**kwargs):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise subprocess.TimeoutExpired(args[0],0)
        kwargs['timeout']=min(kwargs['timeout'],remaining)
        return subprocess.run(*args,**kwargs)
    m.subprocess=types.SimpleNamespace(run=bounded_run)
    # The private library namespace validates this backend creator, while the
    # unchanged helper bytes retain their separate component pin.
    m.source_hash=source_hash
    return m
def locations(base,state):
    root=base.locations(Path(os.environ.get('RUNNER_TEMP',''))/base.STATE_NAME)
    require(state==root/STATE_NAME,'Unexpected backend registry state path')
    return root,root/base.STATE_NAME
def write_state(base,path,value,exclusive=False):
    fd=base.open_file(path,os.O_RDWR|(os.O_CREAT|os.O_EXCL if exclusive else 0))
    with os.fdopen(fd,'w') as stream:
        info=base.checked_file(fd);require(info.st_mode&0o077==0,'Backend state must be private')
        if exclusive:value['state_identity']=base.identity(info)
        require(value['state_identity']==base.identity(info),'Backend state identity changed')
        base.path_matches(path,fd);os.ftruncate(fd,0);json.dump(value,stream,sort_keys=True,allow_nan=False);stream.write('\n');stream.flush();base.path_matches(path,fd)
def read_state(base,path):
    fd=base.open_file(path)
    with os.fdopen(fd,'r') as stream:
        data=json.load(stream);info=base.checked_file(fd)
        require(type(data) is dict and info.st_mode&0o077==0 and data.get('state_identity')==base.identity(info),'Backend state identity/privacy changed')
        base.path_matches(path,fd)
    require(data.get('generator_sha256')==source_hash() and data.get('helper_sha256')==HELPER_SHA
            and type(data.get('uid')) is int and data['uid']==os.getuid(),'Backend state source/principal changed')
    return data
def remove_allocation(base,config,owner):
    """Fresh allocation failure only: guarded inode/descriptor removal before login."""
    fd=os.open(config,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd);require(base.identity(info)==owner['config_identity'] and info.st_uid==os.getuid() and info.st_mode&0o077==0,'Allocation cleanup owner changed')
        base.path_matches(config,fd);names=os.listdir(fd);require(set(names)<={'owner.json','config.json'},'Unexpected allocation entry')
        for name in names:
            child=base.open_file(name,dir_fd=fd);os.close(child)
        for name in names:os.unlink(name,dir_fd=fd)
        base.path_matches(config,fd);os.rmdir(config)
    finally:os.close(fd)
def verify_image(raw,reference,platform):
    require(type(reference) is str and reference in IMAGES and type(platform) is str and platform in {'linux/amd64','linux/arm64'},'Unapproved backend image or platform')
    images=json.loads(raw);require(type(images) is list and len(images)==1 and type(images[0]) is dict,'Backend image inventory malformed')
    image=images[0];arch=platform.split('/')[1]
    require(type(image.get('Id')) is str and image['Id'] in IMAGES[reference][arch]|{reference.partition('@')[2]}
            and image.get('Os')=='linux' and image.get('Architecture')==arch,'Backend immutable image/platform changed')
    digests=image.get('RepoDigests');require(type(digests) is list and bool(digests) and all(type(v) is str for v in digests)
                                           and reference in digests,'Actual normalized Hub repository digest missing')
    return {'image':reference,'image_id':image['Id'],'platform':platform,'repo_digest':reference,'image_verified':True}
def prepare(state,platform):
    require(type(platform) is str and platform in {'linux/amd64','linux/arm64'},'Explicit native backend platform required')
    require(os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch','Backend acquisition requires a trusted manual event')
    username,token=(os.environ.get(n,'') for n in ['DOCKERHUB_USERNAME','DOCKERHUB_TOKEN'])
    require(all(type(v) is str and v and v.strip()==v and not any(c in v for c in '\r\n\0') for v in [username,token]),'Both read-only Hub credentials required')
    base=helper(time.monotonic()+MAX_SECONDS);root,control=locations(base,state)
    require(not state.exists() and not state.is_symlink() and not control.exists() and not control.is_symlink(),'Fresh backend/library states required')
    nonce=uuid4().hex;config=root/('browser-registry-'+nonce);config.mkdir(mode=0o700)
    # Private creator identity is the backend wrapper, never a browser peer.
    # The descriptor/cleanup library remains separately byte-pinned.
    owner={'nonce':nonce,'uid':os.getuid(),'generator_sha256':source_hash(),'registry':REGISTRY,'config':str(config),'config_identity':base.identity(config.stat())}
    data={'generator_sha256':source_hash(),'helper_sha256':HELPER_SHA,'uid':os.getuid(),'status':'ALLOCATED','platform':platform,'images':[],'helper_state':str(control),'credential_owner':owner}
    try:
        base.write_state(config/'owner.json',owner,exclusive=True)
        library={**owner,'status':'ALLOCATED'};base.write_state(control,library,exclusive=True)
        write_state(base,state,data,exclusive=True)
        base.write_state(config/'config.json',{'auths':{'https://index.docker.io/v1/':{'auth':''}}},exclusive=True)
    except BaseException:
        remove_allocation(base,config,owner)
        raise
    try:
        version=base.docker(config,['version','--format','{{json .Server}}']);require(type(version.returncode) is int and version.returncode==0,'Native backend Docker version unavailable')
        server=json.loads(version.stdout);require(type(server) is dict and server.get('Os')=='linux' and server.get('Arch')==platform.split('/')[1],'Requested platform differs from native daemon')
        result=base.docker(config,['login','--username',username,'--password-stdin',REGISTRY],password=(token+'\n').encode())
        require(type(result.returncode) is int,'Backend login invalid exit type');data['login_exit_code']=result.returncode
        require(result.returncode==0,'Backend login failed')
        directory=base.owned_directory(config,owner)
        try:
            fd=base.open_file('config.json',dir_fd=directory)
            with os.fdopen(fd,'r') as stream:
                require(os.fstat(fd).st_mode&0o077==0,'Credential configuration not private');credentials=json.load(stream)
        finally:os.close(directory)
        expected=base64.b64encode((username+':'+token).encode()).decode()
        require(credentials=={'auths':{'https://index.docker.io/v1/':{'auth':expected}}},'Owned backend login configuration mismatch')
        library['status']='AUTHENTICATED_CONFIG_VERIFIED';library['login_exit_code']=0;base.write_state(control,library)
        for reference in IMAGES:
            row={'image':reference,'platform':platform,'image_verified':False};data['images'].append(row);write_state(base,state,data)
            pulled=base.docker(config,['pull','--platform',platform,reference]);require(type(pulled.returncode) is int,'Backend pull invalid exit type');row['pull_exit_code']=pulled.returncode
            require(pulled.returncode==0,'Backend pinned pull failed');write_state(base,state,data)
            inspected=base.docker(config,['image','inspect',reference]);require(type(inspected.returncode) is int,'Backend inspection invalid exit type');row['inspect_exit_code']=inspected.returncode
            require(inspected.returncode==0,'Backend inspection failed');row.update(verify_image(inspected.stdout,reference,platform));write_state(base,state,data)
        data['status']='READY_FOR_CLEANUP';write_state(base,state,data)
        print('Both pinned native backend images acquired; owned credentials require cleanup before candidate checkout')
    except BaseException:
        library['status']='PREPARATION_FAILED';base.write_state(control,library);data['status']='PREPARATION_FAILED';write_state(base,state,data)
        raise
def cleanup(state):
    base=helper(time.monotonic()+60);root,control=locations(base,state);data=read_state(base,state)
    require(data.get('helper_state')==str(control) and data.get('status') in {'ALLOCATED','PREPARATION_FAILED','READY_FOR_CLEANUP'},'Unexpected backend cleanup state')
    library=base.read_json(control);require({key:library.get(key) for key in data['credential_owner']}==data['credential_owner'],'Credential library ownership differs')
    require(type(data.get('credential_owner')) is dict and data['credential_owner'].get('generator_sha256')==source_hash(),'Backend credential creator differs')
    if data['status']=='READY_FOR_CLEANUP':
        require(type(data.get('images')) is list and len(data['images'])==2 and [row.get('image') for row in data['images']]==list(IMAGES)
                and type(data.get('login_exit_code')) is int and data['login_exit_code']==0,'Backend successful preparation inventory differs')
        for row in data['images']:
            require(all(type(row.get(k)) is int and row[k]==0 for k in ['pull_exit_code','inspect_exit_code']) and row.get('image_verified') is True
                    and row.get('platform')==data['platform'] and row.get('repo_digest')==row['image'],'Backend image preparation is incomplete')
            verify_image(json.dumps([{'Id':row['image_id'],'Os':'linux','Architecture':data['platform'].split('/')[1],'RepoDigests':[row['repo_digest']]}]),row['image'],data['platform'])
    else:
        # An interrupted/failed allocation must not reach Docker logout even if
        # the library had verified login before the image preparation stopped.
        library['status']='PREPARATION_FAILED';base.write_state(control,library)
    error=None
    try:base.cleanup(control)
    except BaseException as caught:error=caught
    library=base.read_json(control)
    data.update(status=library['status'],logout_exit_code=library.get('logout_exit_code'),logout_attempted=library.get('logout_attempted'),physical_config_removed=library.get('physical_config_removed'))
    write_state(base,state,data)
    if error is not None:raise error
    print('Owned backend credential configuration physically removed before candidate checkout')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','cleanup']);p.add_argument('--state',type=Path,required=True);p.add_argument('--platform',choices=['linux/amd64','linux/arm64']);args=p.parse_args()
    try:
        if args.mode=='prepare':prepare(args.state,args.platform)
        else:
            require(args.platform is None,'Cleanup does not accept a platform override');cleanup(args.state)
    except Exception:
        print('Owned backend registry acquisition or cleanup refused; inspect nonsensitive state')
        raise SystemExit(1)
class BackendRegistryInterrupted(RuntimeError):
    pass
def run():
    prior={kind:signal.getsignal(kind) for kind in [signal.SIGTERM,signal.SIGINT]}
    def interrupted(signum,frame):raise BackendRegistryInterrupted('Backend registry preparation interrupted')
    try:
        for kind in prior:signal.signal(kind,interrupted)
        main()
    finally:
        for kind,handler in prior.items():signal.signal(kind,handler)
if __name__=='__main__':run()
