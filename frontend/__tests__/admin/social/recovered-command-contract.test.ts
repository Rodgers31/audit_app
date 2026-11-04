import { mediaFileDigest, recoveredSocialCommand, recoverGeneratedRulePath, socialCommandIdentity, socialCommandKey } from '@/lib/api/socialCommandRecovery';
import { SocialApiError } from '@/lib/api/social';
import '../../../tests/socialRecoveryCrypto';
const actor='00000000-0000-4000-8000-000000000001',path='/posts/00000000-0000-4000-8000-000000000010/publish',body={expected_version:1};
beforeEach(()=>{jest.restoreAllMocks();sessionStorage.clear();});
test.each([401,403,409,422,503])('an HTTP%s refusal after a lost response cannot retire the original command',async status=>{
 const send=jest.fn().mockRejectedValueOnce(new Error('Original outcome unknown')).mockRejectedValueOnce(new SocialApiError('PERMISSION_DENIED','Refused now',[],[],false));
 await expect(recoveredSocialCommand(actor,'post',path,body,send)).rejects.toThrow(); const original=send.mock.calls[0][0];
 // The real boundary can reject the retry before receipt lookup. Neither its
 // status nor retryable=false witnesses the outcome of the original attempt.
 await expect(recoveredSocialCommand(actor,'post',path,body,send)).rejects.toThrow();expect(send.mock.calls[1][0]).toBe(original);
 expect(socialCommandKey(actor,socialCommandIdentity(actor,'post',path,body))).toBe(original);
});
test('changed request data never borrows a generated rule path and multiple unresolved matches fail closed',()=>{
 const first='/automation/rules/00000000-0000-4000-8000-000000000011/versions',second='/automation/rules/00000000-0000-4000-8000-000000000012/versions',b={expected_version:0,name:'Reviewed rule'};
 socialCommandKey(actor,socialCommandIdentity(actor,'post',first,b));
 expect(recoverGeneratedRulePath(actor,'post',second,b)).toBe(first);
 expect(recoverGeneratedRulePath(actor,'post',second,{...b,name:'Different rule'})).toBe(second);
 socialCommandKey(actor,socialCommandIdentity(actor,'post',second,b));expect(()=>recoverGeneratedRulePath(actor,'post',second,b)).toThrow();
});
test('FileReader failure identifies the media file rather than claiming the recovery journal is full',async()=>{
 jest.spyOn(FileReader.prototype,'readAsArrayBuffer').mockImplementation(function(this:FileReader){this.dispatchEvent(new ProgressEvent('error'));});
 await expect(mediaFileDigest(new File(['data'],'proof.png',{type:'image/png'}))).rejects.toMatchObject({code:'MEDIA_FILE_READ_FAILED',retryable:true,message:expect.stringContaining('No upload was started')});
});
test('Web Crypto failure produces the same upload-specific diagnostic',async()=>{
 jest.spyOn(crypto.subtle,'digest').mockRejectedValue(new Error('Secure digest unavailable'));
 await expect(mediaFileDigest(new File(['data'],'proof.png',{type:'image/png'}))).rejects.toMatchObject({code:'MEDIA_FILE_READ_FAILED',retryable:true});
});
