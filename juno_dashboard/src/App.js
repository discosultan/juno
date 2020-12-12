import React from 'react';
import { BrowserRouter as Router, Switch, Route, Link as RouterLink } from 'react-router-dom';
import useMediaQuery from '@material-ui/core/useMediaQuery';
import { makeStyles } from '@material-ui/core/styles';
import { createMuiTheme, ThemeProvider } from '@material-ui/core/styles';
import AppBar from '@material-ui/core/AppBar';
import CssBaseline from '@material-ui/core/CssBaseline';
import Link from '@material-ui/core/Link';
import Toolbar from '@material-ui/core/Toolbar';
import Typography from '@material-ui/core/Typography';
import { MuiPickersUtilsProvider } from '@material-ui/pickers';
import DateFnsUtils from '@date-io/date-fns';
import { Dashboard as BacktestDashboard } from './components/backtest';
import { Dashboard as OptimizationDashboard } from './components/optimization';
import Chandler from './chandler';

const useStyles = makeStyles((theme) => ({
  appBarItem: {
    marginRight: theme.spacing(2),
  },
  appBar: {
    zIndex: theme.zIndex.drawer + 1,
  },
}));

const chandler = new Chandler();
export const ChandlerContext = React.createContext();

export default function App() {
  const prefersDarkMode = useMediaQuery('(prefers-color-scheme: dark)');
  const classes = useStyles();

  const theme = React.useMemo(
    () =>
      createMuiTheme({
        palette: {
          type: prefersDarkMode ? 'dark' : 'light',
        },
      }),
    [prefersDarkMode],
  );

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <MuiPickersUtilsProvider utils={DateFnsUtils}>
        <ChandlerContext.Provider value={chandler}>
          <Router>
            <AppBar className={classes.appBar}>
              <Toolbar variant="dense">
                <Link component={RouterLink} to="/backtest" className={classes.appBarItem}>
                  <Typography color="textPrimary" variant="h6">
                    Backtest
                  </Typography>
                </Link>
                <Link component={RouterLink} to="/optimize" className={classes.appBarItem}>
                  <Typography color="textPrimary" variant="h6">
                    Optimize
                  </Typography>
                </Link>
              </Toolbar>
            </AppBar>

            <Switch>
              <Route path="/backtest">
                <BacktestDashboard />
              </Route>
              <Route path="/">
                <OptimizationDashboard />
              </Route>
            </Switch>
          </Router>
        </ChandlerContext.Provider>
      </MuiPickersUtilsProvider>
    </ThemeProvider>
  );
}
