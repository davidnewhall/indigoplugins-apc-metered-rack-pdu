""" Indigo: APC Metered Rack PDU Plugin """


import pexpect
import urllib
import urllib2
import indigo


class Plugin(indigo.PluginBase):
    """ Base Plugin Class for APC Metered Rack """
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.debug = False

    def _refreshStatesFromHardware(self, dev, logRefresh):
        """ Poll all of the states from the APC Metered Rack PDU
            Pass updated values to Indigo Server. """
        keyValueList = []
        try:
            child = self._startCommSSH(dev)
        except:
            indigo.server.log(u"Error connecting to SSH on {0}. Unable to update Device State for: {1}"
                              .format(dev.pluginProps.get("address", "127.0.0.2"), dev.name), isError=True)
            return
        # Temperature
        if dev.temperatureSensorCount == 1:
            child.sendline("tempReading {0}".format(dev.pluginProps["TempScale"]))
            child.expect("apc>")
            temp_str = child.before.splitlines()[2]
            temperature = temp_str.split()[0]
            if logRefresh:
                indigo.server.log(u"received \"{0}\" temperature update to {1}".format(dev.name, temp_str))
            keyValueList.append({"key": "temperatureInput1", "value": temperature, "uiValue": temp_str})
        # Humidity
        if dev.humiditySensorCount == 1:
            child.sendline("humReading")
            child.expect("apc>")
            humidity_str = child.before.splitlines()[2]
            humidity = humidity_str.split()[0]
            if logRefresh:
                indigo.server.log(u"received \"{0}\" humidity update to {1}".format(dev.name, humidity_str))
            keyValueList.append({"key": "humidityInput1", "value": humidity, "uiValue": humidity_str})
        # Power Usage
        if "curEnergyLevel" in dev.states:
            child.sendline("devReading power")
            child.expect("apc>")
            power_str = child.before.splitlines()[2]
            power = power_str.split()[0]
            power = float(power) * 1000
            if logRefresh:
                indigo.server.log(u"received \"{0}\" powerload to {1}".format(dev.name, power_str))
            keyValueList.append({"key": "curEnergyLevel", "value": power, "uiValue": power_str})
        # Energy Consumption
        if "accumEnergyTotal" in dev.states:
            child.sendline("devReading energy")
            child.expect("apc>")
            energy_str = child.before.splitlines()[2]
            energy = energy_str.split()[0]
            if logRefresh:
                indigo.server.log(u"received \"{0}\" energy total to {1}".format(dev.name, energy_str))
            keyValueList.append({"key": "accumEnergyTotal", "value": energy, "uiValue": energy_str})
        self._stopCommSSH(child)
        # Update States
        dev.updateStatesOnServer(keyValueList)

    def _resetEnergy(self, dev):
        """ This method submits POST requests to the APC device to clear the
            energy counters. """
        host = dev.pluginProps.get("address", "127.0.0.2")
        user = dev.pluginProps.get("username", "apc")
        pazz = dev.pluginProps.get("password", "apc")
        values = {"login_username": user, "login_password": pazz, "submit": "Log On"}
        reqdata = urllib.urlencode(values)
        baseurl = "http://{0}".format(host)
        loginurl = "{0}/Forms/login1".format(baseurl)
        try:
            # Post login creds to login URL.
            req = urllib2.Request(loginurl, reqdata)
            response = urllib2.urlopen(req, dev.pluginProps.get("refreshTimeout", 5))
            # Login URL does a redirect. We need the special auth key in the redirect url.
            code = response.geturl()   # http://apc.home.lan/NMC/l271syNoz30Z0XZqS48qWw/
            code = code.split("/")[4]  # l271syNoz30Z0XZqS48qWw
            formurl = "{0}/NMC/{1}/Forms/devcfg1".format(baseurl, code)
            # These are the magic form values that do the reset.
            values = {"Device_kWh_Reset": "on", "Device_Peak_Reset": "on"}
            # And submit the reset to the device form handler.
            reqdata = urllib.urlencode(values)
            req = urllib2.Request(formurl, reqdata)
            if urllib2.urlopen(req, dev.pluginProps.get("refreshTimeout", 5)).getcode() == 200:
                return True
        except:
            indigo.server.log(u"Error polling URL http://{0}: Unable to reset energy usage for: {1}"
                              .format(host, dev.name), isError=True)
        return False

    def _blinkLCD(self, dev):
        """ This method triggers thje LCD to blink.
            Sorta gimmicky, unless you have multiple devices. """
        try:
            child = self._startCommSSH(dev)
        except:
            indigo.server.log(u"Error connecting to SSH on {0}: Unable to communicate with: {1}"
                              .format(dev.pluginProps.get("address", "127.0.0.2"), dev.name), isError=True)
        else:
            child.sendline("lcdblink 1")
            child.expect("apc>")
            child._stopCommSSH()

    def _startCommSSH(self, dev):
        host = dev.pluginProps.get("address", "127.0.0.2")
        user = dev.pluginProps.get("username", "apc")
        pazz = dev.pluginProps.get("password", "apc")
        # Connect
        child = pexpect.spawn("ssh -t {0}@{1}".format(user, host))
        child.timeout = dev.pluginProps.get("refreshTimeout", 5)
        child.setecho(False)
        # Login
        child.expect("password: ")
        child.sendline(pazz)
        child.expect("apc>")
        return child

    def _stopCommSSH(self, child):
        try:
            child.sendline("quit")
            child.close(force=True)
        except:
            indigo.server.log(u"Error closing SSH session.", isError=True)

    ########################################
    def runConcurrentThread(self):
        try:
            while True:
                for dev in indigo.devices.iter("self"):
                    if not dev.enabled or not dev.configured:
                        continue
                    self._refreshStatesFromHardware(dev, dev.pluginProps.get("logChanges", True))
                    self.sleep(int(dev.pluginProps.get("refreshfreq", 60)))

        except self.StopThread:
            pass

    def validateDeviceConfigUi(self, values, type_id, did):
        """ Validate device input. """
        errors = indigo.Dict()
        dev = indigo.devices[did]
        props = dev.pluginProps
        props["NumTemperatureInputs"] = values["NumTemperatureInputs"]
        props["NumHumidityInputs"] = values["NumHumidityInputs"]
        dev.replacePluginPropsOnServer(props)
        return (True, values, errors)

    def actionControlUniversal(self, action, dev):
        """ General Action Callback """
        # Beeper (blink LCD)
        if action.deviceAction == indigo.kUniversalAction.Beep:
            self._blinkLCD(dev)
            indigo.server.log(u"sent \"{0}\" LCD Blink (beep) request".format(dev.name))

        # Energy Update
        elif action.deviceAction == indigo.kUniversalAction.EnergyUpdate:
            self._refreshStatesFromHardware(dev, dev.pluginProps.get("logChanges", True))

        # Reset Energy Counter
        elif action.deviceAction == indigo.kUniversalAction.EnergyReset:
            if self._resetEnergy(dev):
                indigo.server.log(u"sent \"{0}\" energy usage reset".format(dev.name))
                dev.updateStateOnServer("accumEnergyTotal", 0.0)
                self._refreshStatesFromHardware(dev, dev.pluginProps.get("logChanges", True))
            else:
                indigo.server.log(u"sent \"{0}\" energy usage reset - REQUEST FAILED".format(dev.name))

        # Request Status
        elif action.deviceAction == indigo.kUniversalAction.RequestStatus:
            self._refreshStatesFromHardware(dev, dev.pluginProps.get("logChanges", True))
