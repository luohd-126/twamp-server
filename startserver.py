#coding=utf-8

from socket import * 
import socket as sk
import os, sys
from signal import *
from time import sleep
import time
import struct

HOST=''
PORT=862
ctrlConnTimeout = 60    # 控制面连接超时时间，单位为秒 
measTimeout = 30        # 测量面连接超时时间，单位为秒

minPort = 50000
maxPort = 60000

# create socket, reuse port, bind, listen
sockfd = socket()
sockfd.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
address = (HOST, PORT)
sockfd.bind(address)
sockfd.listen(5)

print("Socket created and listening on port 862")

def procSocketError(connfd):
    print ("tcp socket timeout")
    connfd.close()
    return -1

def sendGreetingMsg(connfd):
    greetingMsg = bytearray(64)
    greetingMsg[15] = 0x01

    try: 
        connfd.send(greetingMsg)
        print("send out ====> greeting")
        return 0
    except socket.timeout:
        return procSocketError(connfd)

def waitClientMsg(connfd, msgName, msgLen):
    try:
        data = connfd.recv(1024)
        print("receive <== Client " + msgName + ", expect msg len " + str(msgLen))
        if not data:
            print("client message is invalid")
            return -1
        if len(data) != msgLen:
            print("client message length is invalid")
            return -1
        return 0
    except socket.timeout:
        return procSocketError(connfd)

def sendServerStartMsg(connfd):
    serverStartMsg = bytearray(48)
    # update start-time 
    current_timestamp = time.time()
    seconds = int(current_timestamp)
    fraction = current_timestamp - seconds

    print("current_timestamp = ", current_timestamp)
    # python2.7不支持to_bytes
    # serverStartMsg[32:40] = timestamp_1900.to_bytes(8, byteorder='big')
    serverStartMsg[32:36] = bytearray(struct.pack('>I', seconds))
    serverStartMsg[36:40] = bytearray(struct.pack('>f', fraction))
    try:
        connfd.send(serverStartMsg)
        print("send out ====> server start")
        return 0
    except socket.timeout:
        return procSocketError(connfd)

def sendAcceptSessionMsg(connfd, udpport):
    acceptMsg = bytearray(48)
    # update port 
    acceptMsg[2] = (udpport>>8)&0xFF
    acceptMsg[3] = udpport&0xFF 
    try:
        connfd.send(acceptMsg)
        print("send out ====> accept session")
        return 0
    except socket.timeout:
        return procSocketError(connfd)

def waitStartSessionMsg(connfd):
    try:
        data = connfd.recv(1024)
        if not data:
            print("client start session message is invalid")
            return -1
        if len(data) != 32:
            print("client start session message length is invalid")
            return -2
        if data[0] != 2 and data[0] != '\x02':
            print("client session command invalid ", data[0])
            return -3
        print("receive <== Client start session")
        return 0
    except socket.timeout:
        return procSocketError(connfd)

def sendStartAck(connfd):
    startAckMsg = bytearray(48)
    try:
        connfd.send(startAckMsg)
        print("send out ====> start session ack")
        return 0
    except socket.timeout:
        return procSocketError(connfd)

# deal with client connection
def conn_handler(connfd, udpport):
    # control connections
    print("start conn_handler", connfd.getpeername())
    if (sendGreetingMsg(connfd) != 0): 
        return

    if waitClientMsg(connfd, "setup response msg", 164) != 0:
        return

    if(sendServerStartMsg(connfd) != 0):
        return

    if waitClientMsg(connfd, "request session", 112) != 0:
        return

    if (sendAcceptSessionMsg(connfd, udpport) != 0):
        return

    if waitStartSessionMsg(connfd) != 0:
        return

    if (sendStartAck(connfd) != 0):
        return
    connfd.settimeout(None)

    # meas connections, do meas test 
    udpaddress = ("", udpport)
    print ("udp port:", udpport)
    udpSocket = socket(AF_INET, SOCK_DGRAM)
    udpSocket.bind(udpaddress)
    udpSocket.settimeout(measTimeout)
    print ("waiting udp packet")
    
    seqNo = 0
    try:
        while True:
            data, addr = udpSocket.recvfrom(1024)
            if not data:
                break
            recvTime = time.time() + 2208988800
            print("receive <== host-{}:len-{}:seqNo-{}".format(connfd.getpeername(), len(data), seqNo))
            reflectMsg = bytearray(len(data))
            reflectMsg[0:4] = struct.pack(">I", seqNo)[:4]
            #++seqNo
            seqNo += 1
            reflectMsg[16:20] = struct.pack(">I", int(recvTime))[:4]
            reflectMsg[20:24] = struct.pack(">f", recvTime - int(recvTime))[:4] 
            reflectMsg[24:28] = data[0:4]
            reflectMsg[28:36] = data[4:12]

            sendTime = time.time() + 2208988800
            reflectMsg[4:8] = struct.pack(">I", int(sendTime))[:4]
            reflectMsg[8:12] = struct.pack(">f", sendTime - int(sendTime))[:4]
            #print("seqNo: ", seqNo)
            #print("receive ===data = {}:reflectMsg = {}".format(seqNo, data, reflectMsg))
            udpSocket.sendto(reflectMsg, addr)
            #print("send out hello")
    #except socket.timeout:
    except Exception:
        print ("udp socket timeout")
    udpSocket.close()
    connfd.close()
    sys.exit(0)

# loop handing client request
nextPort = minPort
while True:
    nextPort = nextPort + 1
    if (nextPort > maxPort):
        nextPort = minPort
    try:
        print("waiting for connection ......")
        connfd, address = sockfd.accept()
        connfd.settimeout(ctrlConnTimeout)
        print("new connnections:", address)
    except KeyboardInterrupt:
        print("Quit!")
        sys.exit(1)
    except Exception as e:
        print(e)
        continue

    signal(SIGCHLD, SIG_IGN)

    pid = os.fork()
    if pid < 0:
        print("fork child failed")
        connfd.close()
        continue
    elif pid == 0:
        conn_handler(connfd, nextPort)
    else:
        connfd.close()
        continue
