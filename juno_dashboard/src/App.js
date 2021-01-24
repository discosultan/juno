import React, { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Switch, Route, Link as RouterLink } from 'react-router-dom';
import DateFnsUtils from '@date-io/date-fns';
import AppBar from '@material-ui/core/AppBar';
import CssBaseline from '@material-ui/core/CssBaseline';
import Link from '@material-ui/core/Link';
import Toolbar from '@material-ui/core/Toolbar';
import Typography from '@material-ui/core/Typography';
import {
  ThemeProvider,
  makeStyles,
  // TODO: Remove in MUI v5.
  // https://stackoverflow.com/a/64135466
  unstable_createMuiStrictModeTheme as createMuiTheme,
} from '@material-ui/core/styles';
import useMediaQuery from '@material-ui/core/useMediaQuery';
import { MuiPickersUtilsProvider } from '@material-ui/pickers';

const BacktestDashboard = lazy(() => import('./components/backtest/Dashboard'));
const OptimizationDashboard = lazy(() => import('./components/optimization/Dashboard'));

const useStyles = makeStyles((theme) => ({
  appBarItem: {
    marginRight: theme.spacing(2),
  },
  appBar: {
    zIndex: theme.zIndex.drawer + 1,
  },
}));

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

          <Suspense fallback={<div>Loading...</div>}>
            <Switch>
              <Route path="/backtest" component={BacktestDashboard} />
              <Route path="/" component={OptimizationDashboard} />
            </Switch>
          </Suspense>
        </Router>
      </MuiPickersUtilsProvider>
    </ThemeProvider>
  );
}
