package main

/*
#include <stdlib.h>
*/
import "C"

import (
 "encoding/json"
 "unsafe"

 src "github.com/bogdanfinn/tls-client/cffi_src"
)

//export tlsrequests_call
func tlsrequests_call(input *C.char) *C.char {
 var in src.RequestInput
 if err := json.Unmarshal([]byte(C.GoString(input)), &in); err != nil { return C.CString(`{"status":0,"body":"invalid input"}`) }
 client, session, withSession, clientErr := src.CreateClient(in)
 if clientErr != nil { return C.CString(`{"status":0,"body":"client creation failed"}`) }
 req, clientErr := src.BuildRequest(in)
 if clientErr != nil {
  if withSession { src.RemoveSession(session) }
  b,_:=json.Marshal(src.Response{Status:0, Body:clientErr.Error()}); return C.CString(string(b))
 }
 resp, err := client.Do(req)
 if err != nil {
  if withSession { src.RemoveSession(session) }
  b,_:=json.Marshal(src.Response{Status:0, Body:err.Error()}); return C.CString(string(b))
 }
 cookies := client.GetCookies(resp.Request.URL)
 out, clientErr := src.BuildResponse(session, withSession, resp, cookies, in)
 if clientErr != nil {
  if withSession { src.RemoveSession(session) }
  b,_:=json.Marshal(src.Response{Status:0, Body:clientErr.Error()}); return C.CString(string(b))
 }
 b,err:=json.Marshal(out); if err!=nil { return C.CString(`{"status":0,"body":"response encoding failed"}`) }; return C.CString(string(b))
}

//export tlsrequests_close
func tlsrequests_close(session *C.char) { src.RemoveSession(C.GoString(session)) }

//export tlsrequests_free
func tlsrequests_free(p *C.char) { C.free(unsafe.Pointer(p)) }
func main() {}
