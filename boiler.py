"""
This module implements the boiler proxy
"""

import logging
import queue
import platform
from threading import Thread

from shared import ListenerSender

class BoilerListenerSender(ListenerSender):
    """
    This class implements the boiler proxy
    """
    def __init__(self, sq: queue.Queue, src_iface: bytes,dst_iface: bytes):
        super().__init__(sq, src_iface, dst_iface)
        # Add any additional initialization logic here
        self.rq = queue.Queue()

    def handle_first(self, data, addr):
        if self.bound is False:
            logging.debug('BoilerListenerSender first packet, listener not bound yet')
            # first time we receive a packet, bind from the source port
            logging.info('BoilerListenerSender discovered %s:%d', addr[0], addr[1])
            self.bl_addr = addr[0]
            self.bl_port = addr[1]
            self.sq.put('BL_ADDR:'+self.bl_addr)
            self.sq.put('BL_PORT:'+str(self.bl_port))
            self.resend.bind(('', self.bl_port))
            logging.debug('sender bound to port: %d', self.bl_port)
            self.bound = True

    def send(self, data):
        logging.debug('resending %d bytes to %s : %d',
                      len(data), self.gw_addr.decode(), self.gw_port)
        self.resend.sendto(data, (self.gw_addr, self.gw_port))
        logging.info('resent %d bytes to %s : %d',
                     len(data), self.gw_addr.decode(), self.gw_port)

    def discover(self):
        """ This method discovers the gateway ip address and port. ip address and port."""
        while self.gw_port == 0:
            self.handle()

    def bind(self):
        """ This method binds the listener mimicking the gateway."""
        if platform.system() == 'Darwin':
            self.listen.bind( ('',self.gw_port+1) )
            logging.debug('listener bound to %s, port %d', self.src_iface.decode(), self.gw_port+1)
        else:
            self.listen.bind( ('',self.gw_port) )
            logging.debug('listener bound to %s, port %d', self.src_iface.decode(), self.gw_port)

class ThreadedBoilerListenerSender(Thread):
    """
    This class implements a Thread to run the boiler proxy
    """
    bls: BoilerListenerSender

    def __init__(self, sq: queue.Queue, src_iface: bytes,dst_iface: bytes):
        super().__init__()
        self.bls= BoilerListenerSender(sq, src_iface, dst_iface)

    def queue(self) -> queue.Queue:
        """
        This method returns the queue to receive data from.
        """
        return self.bls.queue()

    def run(self):
        logging.info('BoilerListenerSender started')
        self.bls.discover()
        self.bls.bind()
        self.bls.loop()
