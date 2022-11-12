# Implement a telnet to UART bridge for retrocomputers
# This version has been tested with Lee Hart's Z80 Mem­ber­ship Card
# http://www.sunrise-ev.com/z80.htm
#
# This could be implemented in C for performance, but with MicroPython
# it's easy to edit the parameters on any computer.
#
# Thanks to https://github.com/cpopp/MicroTelnetServer for some
# ideas.
#
# Also note that it's good to get started with a simple terminal
# program such as minicom and https://github.com/Noltari/pico-uart-bridge
# and then try this program after the basics are working.
#
# See https://github.com/Noltari/pico-uart-bridge/releases for UF2 files.
#
import machine
import network
import rp2
import socket
import time

# Parameters which you may want to change
#
HOSTNAME = "Z80MembershipCard" # not supported yet, pybd hardcoded
TELNET_PORT = 23
TELNET_LED_PIN = 15
UART_TX_PIN = 16
UART_RX_PIN = 17
UART_BAUDRATE = 9600 # change for different retro needs
CONSOLE_DEBUG = False

# The secrets file should have the following contents:
# SSID = 'yourssidstring'
# PASSWORD = 'yourpasswordstring'
#
import secrets

# UART initialization
uart0 = machine.UART(0, baudrate=UART_BAUDRATE, tx=machine.Pin(UART_TX_PIN), rx=machine.Pin(UART_RX_PIN))

if CONSOLE_DEBUG:
    print('Starting telnet server')

wifiLed = machine.Pin("LED", machine.Pin.OUT)
wifiLed.off()

telnetLed = machine.Pin(TELNET_LED_PIN, machine.Pin.OUT)
telnetLed.off()

# Country code for wireless network
rp2.country('US')

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
#wlan.config(hostname=HOSTNAME)
wlan.config(pm = 0xa11140) # don't enter power savings mode
wlan.connect(secrets.SSID, secrets.PASSWORD)

# Wait for connect or fail
if CONSOLE_DEBUG:
    print('Waiting for connection...')

max_wait = 100
while max_wait > 0:
    if wlan.status() < 0 or wlan.status() >= 3:
        break
    max_wait -= 1
    wifiLed.toggle()
    time.sleep(0.1)

wifiLed.on()

# Handle connection error
if wlan.status() != 3:
    raise RuntimeError('Network connection failed')
else:
    status = wlan.ifconfig()
    if CONSOLE_DEBUG:
        print( 'Connected with IP = ' + status[0] )
    wifiLed.on()
    
# Open socket
#
addr = socket.getaddrinfo('0.0.0.0', TELNET_PORT)[0][-1]

server_socket = socket.socket()
server_socket.bind(addr)
server_socket.listen(1)

if CONSOLE_DEBUG:
    print('Listening on', addr)

# Listen for connections
while True:
    try:
        client_socket, remote_addr = server_socket.accept()
        client_socket.setblocking(False)
        if CONSOLE_DEBUG:
            print('Client connected from', remote_addr)
        telnetLed.on()
        
        # Stack Overflow answer from Jack
        # https://stackoverflow.com/questions/273261/force-telnet-client-into-character-mode
        # IAC WILL ECHO IAC WILL SUPPRESS_GO_AHEAD IAC WONT LINEMODE
        # 255  251    1 255  251                 3 255  252       34
        client_socket.sendall(bytes([255,251,1,255,251,3,255,252,34]))

        client_file = client_socket.makefile('rwb', 0)
        
        uartRxData = bytes()
        discard_count = 0
        connectedSocket = True
        
        while connectedSocket:
            # Telnet -> UART TX

            # We get a character at a time in the hopes that the
            # character and line delays used by the client will
            # be respected. Not sure if this is a good idea, might
            # want to switch to readline and implement delays locally
            telnetRxData = client_file.read(1)
            if telnetRxData == b'':
                # Disconnected socket
                connectedSocket = False
                #client_socket.close()
            elif telnetRxData:
                telnetRxByte = telnetRxData[0]
                # Discard telnet control characters, pass all others
                if telnetRxByte == 0xff:
                    discard_count = 2
                elif discard_count != 0:
                    discard_count -= 1
                else:
                    uart0.write(telnetRxData)
                    
            # UART RX -> Telnet
            
            # We get a character at a time. Similar approach as with
            # the socket. Hopefully this improves interactivity.
            if uart0.any() > 0:
                uartRxData = uart0.read(1)
                writtenToSocket = 0
                while writtenToSocket != 1:
                    try:
                        writtenToSocket = client_socket.send(uartRxData)
                    except OSError as e:
                        if len(e.args) > 0 and e.args[0] == errno.EAGAIN:
                            # Try again
                            writtenToSocket = 0
                            pass
                        else:
                            # A serious problem
                            raise
        if CONSOLE_DEBUG: 
            print('Detected disconnected socket')
        client_socket.close()
        telnetLed.off()
        
    except OSError as e:
        client_socket.close()
        if CONSOLE_DEBUG:
            print('Connection closed due to exception')
