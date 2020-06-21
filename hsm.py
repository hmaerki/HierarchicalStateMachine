import inspect
import cStringIO
import re

objRegexpSpaces = re.compile('^(?P<spaces>.*?)(\S(.*)$)', re.M)

class StateChangeException(Exception):
  def __init__(self, methNewState):
    Exception.__init__(self, 'New state is: %s' % (methNewState.__name__))
    self.methNewState = methNewState

class IgnoreEventException(Exception):
  pass

class DontChangeStateException(Exception):
  pass

class BadStatemachineException(Exception):
  def __init__(self, strMsg):
    Exception.__init__(self, strMsg)

class Statemachine:
  def __init__(self):
    def funcNoLog(strLine):
      pass
    self.funcLogMain = funcNoLog
    self.funcLogSub = funcNoLog
    self.private_strStateActual = 'NOT-INITIALIZED-YET'

  def getState(self):
    return self.private_strStateActual

  def setMiniLogger(self):
    def funcLogMain(strLine):
      print strLine
    def funcLogSub(strLine):
      print '  ' + strLine
    self.funcLogMain = funcLogMain
    self.funcLogSub = funcLogSub

  def setLogger(self, funcLogMain, funcLogSub):
    """
      Tell the statemachine where to log
    """
    self.funcLogMain = funcLogMain
    self.funcLogSub = funcLogSub

  def dispatch(self, objSignal):
    strStateBefore = self.private_strStateActual

    try:
      self.funcLogMain('%s: will be handled by %s' % (repr(objSignal), self.private_strStateActual))
      self.funcLogSub('  calling state "state_%s(%s)"' % (strStateBefore, str(objSignal)))
      strHandlingState = self.private_strStateActual
      while True:
        meth = getattr(self, 'state_' + strHandlingState)
        meth(objSignal)
        i = strHandlingState.rfind('_')
        if i<0:
          raise Exception("Signal %s was not handled!" % str(objSignal))
          # print "Empty Transition!"
          # return
        strHandlingState = strHandlingState[:i]
      return
    except DontChangeStateException, e:
      self.funcLogSub("  No state change!")
      return
    except IgnoreEventException, e:
      self.funcLogSub("  Empty Transition!")
      return
    except StateChangeException, e:
      self.funcLogSub("%s: was handled by state_%s" % (str(objSignal), strHandlingState))
      # Evaluate init-state
      strNewState = e.methNewState.__name__.replace('state_', '')
      strInitState = self.get_init_state(strNewState)
      if strInitState != strNewState:
        self.funcLogSub('  Init-State for %s is %s.' % (strNewState, strInitState))
      self.private_strStateActual = strInitState

    # Call the exit/entry-actions
    self.callExitEntryActions(objSignal, strStateBefore, strInitState)

  def get_init_state(self, strState):
    try:
      return self.get_init_state(self.private_dictInitState[strState])
    except KeyError, e:
      return strState

  def get_method_list(self, strType):
    import inspect
    results = []
    for strKey in dir(self):
      objValue = getattr(self, strKey)
      if inspect.ismethod(objValue):
        # if objValue.__name__.find(strType) == 0:
        if strKey.find(strType) == 0:
          # results.append(objValue.__name__[len(strType):])
          results.append(strKey[len(strType):])
    results.sort()
    return results

  def callExitEntryActions(self, objSignal, strStateBefore, strStateAfter):
    listStateBefore = strStateBefore.split('_')
    listStateAfter = strStateAfter.split('_')

    # Find toppest state
    iToppestState = 0
    for strBefore, strAfter in zip(listStateBefore, listStateAfter):
      if strBefore != strAfter:
        break
      iToppestState += 1

    # Call all Exit-Actions
    for i in range(len(listStateBefore), iToppestState, -1):
      strState = '_'.join(listStateBefore[:i])
      try:
        fExit = getattr(self, 'exit_' + strState)
      except AttributeError, e:
        pass
      else:
        self.funcLogSub('  Calling %s' % (fExit.__name__))
        fExit()
    # Call all Entry-Actions
    for i in range(iToppestState, len(listStateAfter)):
      strState = '_'.join(listStateAfter[:i+1])
      try:
        fEntry = getattr(self, 'entry_' + strState)
      except AttributeError, e:
        pass
      else:
        self.funcLogSub('  Calling %s' % (fEntry.__name__))
        fEntry(objSignal)

    return

  def get_top_state_obsolete(self, listStates):
    strTopState = None
    for strState in listStates:
      if len(strState.split('_')) == 1:
        strTopState = strState
    if strTopState == None:
      raise BadStatemachineException('No Top State found')
    return strTopState

  def consistency_check(self):
    for strAction, list in (('entry_', self.private_listEntryNames), ('exit_', self.private_listExitNames)):
      for strEntry in list:
        try:
          meth = getattr(self, 'state_' + strEntry)
          pass
        except AttributeError, e:
          raise BadStatemachineException('No corresponding state_%s() for %s%s()!' % (strEntry, strAction, strEntry))

  def reset(self):
    self.private_listStateNames = self.get_method_list('state_')
    self.private_listInitNames = self.get_method_list('init_')
    self.private_listEntryNames = self.get_method_list('entry_')
    self.private_listExitNames = self.get_method_list('exit_')
    self.private_dictInitState = {}
    for strInitState in self.private_listInitNames:
      objValue = getattr(self, 'init_' + strInitState)
      self.private_dictInitState[strInitState] = objValue.__name__[len('state_'):]

    # self.get_top_state_obsolete(self.private_listStateNames)

    # Find top state
    # self.strTopState = self.get_top_state_obsolete(self.private_listStateNames)
    if not self.private_dictInitState.has_key(''):
      raise BadStatemachineException('Init-State on top-level is required but missing. Example "init_ = state_XYZ".')
    # self.strTopState = self.private_dictInitState['']
    
    # Evaluate the init-state
    # self.private_strStateActual = self.get_init_state(self.strTopState)
    self.private_strStateActual = self.get_init_state('')
    
    # Verify validity of the entry and exit actions
    self.consistency_check()
    
    import inspect
    listMembers = inspect.getmembers(self)
    for strType, objValue in listMembers:
      if inspect.ismethod(objValue):
        pass
        # print 'method: ' + strType + '->' + objValue.__name__
    pass

  def start(self):
    # Call the entry-actions
    # self.callExitEntryActions(self.strTopState, self.private_strStateActual)
    self.callExitEntryActions(None, '', self.private_strStateActual)

  def _beautify_docstring(self, strDocString):
    strDocString = '\n' + strDocString.replace('\r\n', '\n')
    strDocString = strDocString.replace('\r', '')
    # remove empty lines at the begin
    objMatch = objRegexpSpaces.search(strDocString)
    if objMatch:
      strSpaces = objMatch.groupdict(0)['spaces']
      strDocString = strDocString.replace('\n' + strSpaces, '\n')
    strDocString = strDocString.strip()
    strDocString = strDocString.replace('\n', '<br>\n')
    return strDocString.replace(' ', '&nbsp;')

  def get_docstring(self, strAttrName):
    strDocString = inspect.getdoc(getattr(self, strAttrName))
    if strDocString:
      # strDocString = strDocString.strip().replace('\n', '<br>')
      return self._beautify_docstring(strDocString)
    return ""

  def get_hierarchy_(self, strParentState=''):
    listLevel = []
    for strState in self.private_listStateNames:
      if strState.find(strParentState) != 0:
        continue
      if len(strState.split('_')) == len(strParentState.split('_'))+1:
        strName = strState.split('_')[-1]
        listLevel.append({
          'fullname': strState,
          'name': strName,
          'substates': self.get_hierarchy(strState)
        })
        continue
    return listLevel

  def get_hierarchy(self, strParentState=None):
    listLevel = []
    for strState in self.private_listStateNames:
      if not strParentState:
        if len(strState.split('_')) == 1:
          listLevel.append((strState, self.get_hierarchy(strState)))
        continue
      if strState.find(strParentState) != 0:
        continue
      if len(strState.split('_')) != len(strParentState.split('_'))+1:
        continue
      listLevel.append((strState, self.get_hierarchy(strState)))
    return listLevel

  def doc_state(self, strState):
    import cStringIO
    f = cStringIO.StringIO()
    f.write('<table class="table_state">')
    f.write('  <tr>')
    f.write('    <td class="td_header" colSpan="3">%s</td>' % strState.split('_')[-1])
    f.write('  </tr>')
    strDocstring = self.get_docstring('state_'+strState)
    if strDocstring:
      f.write('<tr class="tr_comment">')
      f.write('	<td class="td_space">&nbsp;&nbsp;&nbsp;</td>')
      f.write('	<td class="td_label">comment</td>')
      f.write('	<td class="td_text">%s</td>' % strDocstring)
      f.write('</tr>')
    if strState in self.private_listInitNames:
      strInitState = self.private_dictInitState[strState]
      f.write('<TR class="tr_init">')
      f.write('	<TD></TD>')
      f.write('	<TD class="td_label">init</TD>')
      f.write('	<TD class="td_text">%s</TD>' % strInitState)
      f.write('</TR>')
    if strState in self.private_listEntryNames:
      strDocstring = self.get_docstring('entry_'+strState)
      if strDocstring:
        f.write('<TR class="tr_entry">')
        f.write('	<TD></TD>')
        f.write('	<TD class="td_label">entry</TD>')
        f.write('	<TD class="td_text">%s</TD>' % strDocstring)
        f.write('</TR>')
    if strState in self.private_listExitNames:
      strDocstring = self.get_docstring('exit_'+strState)
      if strDocstring:
        f.write('<TR class="tr_exit">')
        f.write('	<TD></TD>')
        f.write('	<TD class="td_label">exit</TD>')
        f.write('	<TD class="td_text">%s</TD>' % strDocstring)
        f.write('</TR>')
    if False:
      bShowSource = False
      if bShowSource:
        strSource = inspect.getsource(getattr(self, 'state_'+strState))
        if not strSource:
          strSource = '&nbsp;'
        f.write('<td valign="top" height="100%"><pre class="small">' + strSource + '</pre></td>')
    return f.getvalue(), '</table>'


  def doc_state_recursive(self, listStates):
    f = cStringIO.StringIO()
    for strState, listStates in listStates:
      strStateBegin, strStateEnd = self.doc_state(strState)
      strStateSub = self.doc_state_recursive(listStates)
      f.write(strStateBegin)
      if strStateSub:
        f.write('  <tr class="tr_sub">')
        f.write('  	<td class="td_space">&nbsp;&nbsp;&nbsp;</td>')
        f.write('  	<td class="td_substate" colSpan="2">')
        f.write(strStateSub)
        f.write('  	</td>')
        f.write('  </tr>')
      f.write(strStateEnd)
    return f.getvalue()

  def doc(self):
    """
      Return a HTML-Page which describes the HSM
    """
    bShowSource = False
    f = cStringIO.StringIO()
    f.write(html_header)
    strDocstring = inspect.getdoc(self)
    if strDocstring:
      f.write('<p>' + strDocstring + '</p><br>')
    listHierarchy = self.get_hierarchy()
    s = self.doc_state_recursive(listHierarchy)
    f.write(s)
    f.write('</body>\n')
    f.write('</html>\n')
    return f.getvalue()

html_header = """
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<?xml version="1.0" encoding="iso-8859-1" ?>
<html xmlns="http://www.w3.org/1999/xhtml">
	<head>
		<title>Hierarchical State Machine</title> 
		<meta http-equiv="content-type" content="text/html;charset=iso-8859-1">
		<meta content="Zulu Website-Assembler v2.1.3" name="assembler">
		<meta content="Zulu by Positron and Maerki Informatik" name="description">
		<meta content="Zulu Website Assembler Positron Maerki Informatik Schweiz Switzerland"
			name="keywords">
		<style type="text/css">
		<!--
		/*  common styles  */
		table.table_state {width: 100%; border-left: 2px solid #000000; border-right: 2px solid #000000; border-top: 0px solid #000000; border-bottom: 0px solid #000000}
		td.td_header { background-color: #EEEEEE; border-bottom: 1px solid #000000; border-top: 1px solid #000000; font-weight: bold}
		td.td_label {width: 1%; font-size: smaller; font-style: italic}
		td.td_text {font-size: smaller}
		td.td_space {width: 1%}
		td.td_substate {width: 100%}
		-->
		</style>
	</head>
	<body>
"""

#class Test_NoTopState(Statemachine):
#  """
#    >>> sm = Test_NoTopState()
#    >>> sm.reset()
#    Traceback (most recent call last):
#    ...
#    BadStatemachineException: No Top State found
#  """
#  def state_TopA_SubB(self, objSignal):
#    pass
#  init_ = state_TopA_SubB

class Test_UnmatchedEntryAction(Statemachine):
  """
    >>> sm = Test_UnmatchedEntryAction()
    >>> sm.reset()
    Traceback (most recent call last):
    ...
    BadStatemachineException: No corresponding state_TopA_SubB() for entry_TopA_SubB()!
  """
  def state_TopA(self, objSignal):
    pass
  def entry_TopA_SubB(self, objSignal):
    pass
  init_ = state_TopA

class Test_UnmatchedExitAction(Statemachine):
  """
    >>> sm = Test_UnmatchedExitAction()
    >>> sm.reset()
    Traceback (most recent call last):
    ...
    BadStatemachineException: No corresponding state_TopA_SubB() for exit_TopA_SubB()!
  """
  def state_TopA(self, objSignal):
    pass
  def exit_TopA_SubB(self):
    pass
  init_ = state_TopA

class Test_SimpleStatemachineTopStateHandlesSignal(Statemachine):
  """
    >>> sm = Test_SimpleStatemachineTopStateHandlesSignal()
    >>> sm.reset()
    >>> sm.setMiniLogger()
    >>> sm.dispatch('a')
    'a': will be handled by TopA_SubA
        calling state "state_TopA_SubA(a)"
        No state change!
  """
  def state_TopA(self, objSignal):
    if (objSignal == 'a'):
      raise DontChangeStateException
  def state_TopA_SubA(self, objSignal):
    if (objSignal == 'b'):
      raise StateChangeException(self.state_TopA_SubB)
  init_ = state_TopA_SubA


class Test_SimpleStatemachine(Statemachine):
  """
    >>> sm = Test_SimpleStatemachine()
    >>> sm.reset()
    >>> sm.setMiniLogger()
    >>> sm.dispatch('a')
    'a': will be handled by TopA
        calling state "state_TopA(a)"
      a: was handled by state_TopA
    >>> sm.dispatch('b')
    'b': will be handled by TopA_SubA
        calling state "state_TopA_SubA(b)"
      b: was handled by state_TopA_SubA
        Calling entry_TopA_SubB
    >>> sm.dispatch('b')
    'b': will be handled by TopA_SubB
        calling state "state_TopA_SubB(b)"
        Empty Transition!
    >>> sm.dispatch('a')
    'a': will be handled by TopA_SubB
        calling state "state_TopA_SubB(a)"
      a: was handled by state_TopA
        Calling exit_TopA_SubB
  """
  def state_TopA(self, objSignal):
    if (objSignal == 'a'):
      raise StateChangeException(self.state_TopA_SubA)
    raise IgnoreEventException()
  def state_TopA_SubA(self, objSignal):
    if (objSignal == 'b'):
      raise StateChangeException(self.state_TopA_SubB)
  def state_TopA_SubB(self, objSignal):
    pass
  def exit_TopA_SubB(self):
    pass
  def entry_TopA_SubB(self, objSignal):
    pass
  init_ = state_TopA

class Test_StatemachineWithEntryExitActions(Statemachine):
  """
    >>> sm = Test_StatemachineWithEntryExitActions()
    >>> sm.reset()
    >>> sm.setMiniLogger()
    >>> sm.dispatch('r')
    'r': will be handled by TopA
        calling state "state_TopA(r)"
      r: was handled by state_TopA
        Calling exit_TopA
        Calling entry_TopC
    >>> sm.dispatch('s')
    's': will be handled by TopC
        calling state "state_TopC(s)"
      s: was handled by state_TopC
        Calling exit_TopC
        Calling entry_TopB
        Calling entry_TopB_SubA
        Calling entry_TopB_SubA_SubsubA
    >>> sm.dispatch('t')
    't': will be handled by TopB_SubA_SubsubA
        calling state "state_TopB_SubA_SubsubA(t)"
      t: was handled by state_TopB_SubA_SubsubA
        Calling exit_TopB_SubA_SubsubA
        Calling exit_TopB_SubA
        Calling exit_TopB
        Calling entry_TopC

    Traceback (most recent call last):
    ...
    Exception: Signal c was not handled!
  """
  def state_TopA(self, objSignal):
    raise StateChangeException(self.state_TopC)
  def exit_TopA(self):
    pass
  def state_TopB(self, objSignal):
    pass
  def entry_TopB(self, objSignal):
    pass
  def exit_TopB(self):
    pass
  def state_TopB_SubA(self, objSignal):
    pass
  def entry_TopB_SubA(self, objSignal):
    pass
  def exit_TopB_SubA(self):
    pass
  def state_TopB_SubA_SubsubA(self, objSignal):
    raise StateChangeException(self.state_TopC)
  def entry_TopB_SubA_SubsubA(self, objSignal):
    pass
  def exit_TopB_SubA_SubsubA(self):
    pass
  def state_TopC(self, objSignal):
    raise StateChangeException(self.state_TopB_SubA_SubsubA)
  def entry_TopC(self, objSignal):
    pass
  def exit_TopC(self):
    pass
  init_ = state_TopA


def test():
  import doctest, hsm
  return doctest.testmod(hsm)

if __name__ == "__main__":
  test()