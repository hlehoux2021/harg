#!/usr/bin/python
# -*- coding: utf-8 -*-

# 100.84: <broadcast>	50000->35601	HargaWebApp
# 100.84: <broadcast>	50002->50001	hargassner.diagnostics.request
# 100.84: <broadcast>	50000->35601	get services
# 100.13: 100.84	35601->50000	HSV/CL etc *.cgi
# 100.84: 100.13	51975-->23	$login token
# 100.13: 100.84	23-->51975	$3313C1
# 100.13: 100.84	23->51975	F2\r\n
# 100.84: 100.13	51975->23	$login key 137171BD37643C72131D59797D966A730E\r\n
# 100.13: 100.84	23->51975	zclient login (7421)\r\n$ack\r\n

import socket,select
import time
import logging
import sys
from threading import Thread, Lock
import signal

#----------------------------------------------------------#
UDP_PORT= 35601 # destination port to which gateway is broadcasting
SRC_IFACE= b"eth0"
DST_IFACE= b"wlan0" # interface of destination vlan
LOG_PATH = "/home/pi/harg/" #chemin où enregistrer les logs
SOCKET_TIMEOUT= 0.2
BUFF_SIZE= 1024
#----------------------------------------------------------#

gw_port = 0 # source port from which gateway is sending broadcasts
gwt_port= 0 # source port from which gateway connects telnet session
gw_addr= b''
bl_addr= b''

#----------------------------------------------------------#
#        definition des logs                               #
#----------------------------------------------------------#
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('log')
logger.setLevel(logging.DEBUG) # choisir le niveau de log : DEBUG, INFO, ERROR...

handler_debug = logging.FileHandler(LOG_PATH + "trace.log", mode="a", encoding="utf-8")
handler_debug.setFormatter(formatter)
handler_debug.setLevel(logging.DEBUG)
logger.addHandler(handler_debug)

def telnet_proxy(lock, src_iface, dst_iface, port):
	try:
		global gw_addr
		global gwt_port
		global bl_addr

		logger.debug('telnet started: %s , %s', src_iface, dst_iface)
		listen= socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		listen.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, src_iface)
		listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
		listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

		logger.debug('telnet binding to port %s', port)
		try:
			listen.bind( ('', port) )
		except:
			logger.error('telnet binding failed on %d',port)
			raise

		logger.debug('telnet listenning')
		listen.listen(4)

		logger.debug('telnet accepting a connection')
		telnet, addr = listen.accept()
		logger.debug('telnet connection from %s:%d accepted', addr[0], addr[1])
		if addr[0] !=  gw_addr:
			logger.error('%s connected to telnet whereas should be the gateway on %s', addr[0], gw_addr)
		lock.acquire()
		gwt_port= addr[1] # remember source_port
		lock.release()

		#we will now create the socket to resend the telnet request
		resend= socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		resend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
		resend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		resend.settimeout(SOCKET_TIMEOUT)

		logger.info('connecting to %s:%d', bl_addr.decode(), port) 
		try :
			resend.connect( (bl_addr,port) )
		except :
			logger.error('connection to %s:%d failed, exiting', bl_addr.decode(), port)

		socket_list= [telnet, resend]
		while True:
			read_sockets, write_sockets, error_sockets = select.select(socket_list , [], [])
			for sock in read_sockets:
				if sock==telnet:
					#so we received a request
					data, addr = telnet.recvfrom(BUFF_SIZE)
					logger.info('telnet received  request %d bytes from  %s:%d ==>%s', len(data), addr[0], addr[1], data.decode() )
					#we should resend it
					logger.info('resending %d bytes to %s:%d', len(data), bl_addr.decode(), port)
					resend.send(data)
				if sock==resend:
					#so we received a reply
					data, addr = resend.recvfrom(BUFF_SIZE)
					logger.info('telnet received response %d bytes from  %s:%d ==>%s', len(data), addr[0], addr[1], data.decode() )

					logger.debug('sending %d bytes to %s:%d', len(data), gw_addr.decode(), gwt_port )
					telnet.send(data)
					logger.info('telnet sent back response to client')
	except:
		logger.error('exception raised')
		listen.close()
		resend.close()

def listen_and_resend(lock, src_iface,dst_iface, mode='gateway'):
	global gw_port
	global gw_addr

	try:
		logger.debug('listen_and_resend started: %s , %s : mode=%s',src_iface,dst_iface,mode)
		listen= socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)  # UDP
		listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
		listen.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
		listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		listen.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, src_iface)

		#lock.acquire()
		if mode=='gateway':
			try:
				listen.bind( ('',UDP_PORT) )
			except:
				logger.error('%s bind() failed on %d',mode,UDP_PORT)
				raise
			logger.debug('%s listener bound to %s, port %d', mode, src_iface.decode(), UDP_PORT)
		else:
			while gw_port == 0:
				logger.warning('%s , skipping bind to gateway source port, since unknown yet',mode)
				time.sleep(5)
			logger.debug('%s binding listener to %s:%d',mode,src_iface.decode(), gw_port)
			try:
				listen.bind( ('',gw_port) )
			except:
				logger.error('%s listen.bind() failed on %d (%s)',mode,gw_port,src_iface)
				raise
			logger.debug('%s listener bound to %s, port %d', mode, src_iface.decode(), gw_port)
		#lock.release()

		resend= socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
		resend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
		resend.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
		resend.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, dst_iface) # bind to vlan iface
		resend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		resend.settimeout(SOCKET_TIMEOUT)

		bound= False
		while True:
			logger.debug('%s waiting data',mode)
			data, addr = listen.recvfrom(1024)
			logger.info('%s received buffer of %d bytes from %s : %d', mode, len(data), addr[0], addr[1])
			if bound == False:
				logger.debug('%s resend not bound yet',mode) 
				# first time we receive a packet, bind from the source port
				lock.acquire()
				if mode=='gateway':
					gw_port= addr[1]
					gw_addr= addr[0]
					logger.info('gateway identified by  %s:%d',gw_addr,gw_port)
					try:
						resend.bind( ('',gw_port) );
					except:
						logger.error('%s resend.bind() failed on %d (%s)',mode,gw_port,dst_iface)
						raise
					logger.debug('%s resender bound to %s :  %d', mode, dst_iface.decode(), gw_port)
					bound = True
				else:
					logger.info('%s not gateway:todoif bind needed %s:%d',mode,addr[0],addr[1])
				lock.release()
			# now would resend the packet on destination
			if mode=='gateway':
				resend.sendto(data, ('<broadcast>', UDP_PORT) )
				logger.info('%s resent %d bytes to %s : %d', mode, len(data), dst_iface.decode(), UDP_PORT)
			else:
				if gw_port==0:
					logger.warning('%s , skipping resend to gateway, since port unknown yet',mode)
				else:
					logger.info('%s resending %d bytes to %s : %d', mode,len(data), gw_addr, gw_port)
					resend.sendto(data, (gw_addr, gw_port) )
					logger.info('%s resent %d bytes to %s : %d', mode, len(data),  gw_addr, gw_port)

	except:
		logger.error('exception raised')
		listen.close()
		resend.close()

# main -------------#
logger.info('starting')

# we will create a Lock() to synchronize threads access to shared data
#mind bl_port is defined in UDP_PORT global
lock= Lock()

#listener(SRC_IFACE, DST_IFACE, UDP_PORT)
try:
	#  start a thread to listen to gateway broadcast messages and rebroadcast to boiler vlan
	t1= Thread(target=listen_and_resend,  args=(lock, SRC_IFACE, DST_IFACE, 'gateway') )
	t1.start()

	# start a thread to listen to boiler(vlan/interface) answers
#	t2= Thread(target=listen_and_resend, args=(lock, DST_IFACE, SRC_IFACE, 'boiler') )
#	t2.start()


	t3= Thread(target=telnet_proxy, args=(lock, SRC_IFACE, DST_IFACE, 23) )
	time.sleep(10)
	t3.start()

	signal.pause()

except (KeyboardInterrupt, SystemExit):
	logger.warning('Received keyboard interrupt, quitting threads.')

#t1.join()
#t2.join()
logger.info('exit main')

