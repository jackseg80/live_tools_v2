import sys
sys.path.append('../..')
import ta
import numpy as np
import pandas as pd
from utilities.bt_analysis import get_n_columns, get_metrics
from utilities.VaR import ValueAtRisk
import copy

class BollingerTrendMulti():
    def __init__(
        self,
        df_list,
        oldest_pair,
        parameters_obj,
        type=["long"],
    ):
        self.df_list = df_list
        self.oldest_pair = oldest_pair
        self.parameters_obj = parameters_obj
        self.use_long = True if "long" in type else False
        self.use_short = True if "short" in type else False
        
    def populate_indicators(self, show_log=False):
        # -- Clear dataset --
        for pair in self.df_list:
            df = self.df_list[pair]
            params = self.parameters_obj[pair]
            df.drop(columns=df.columns.difference(['open','high','low','close','volume']), inplace=True)
            
            # -- Populate indicators --
            bol_band = ta.volatility.BollingerBands(close=df["close"], window=params["bb_window"], window_dev=params["bb_std"])
            df["lower_band"] = bol_band.bollinger_lband()
            df["higher_band"] = bol_band.bollinger_hband()
            df["ma_band"] = bol_band.bollinger_mavg()

            df['long_ma'] = ta.trend.sma_indicator(close=df['close'], window=params["long_ma_window"])
            df['iloc'] = range(len(df))

            df = get_n_columns(df, ["ma_band", "lower_band", "higher_band", "close"], 1)
            
            self.df_list[pair] = df
            # -- Log --
            if(show_log):
                print(self.df_list[self.oldest_pair])
                
        return self.df_list[self.oldest_pair]
    
    def populate_buy_sell(self, show_log=False): 
        data_open_long = []
        data_close_long = []
        data_open_short = []
        data_close_short = []

        for pair in self.df_list:
            df = self.df_list[pair]
            # -- Initiate populate --
            df["open_long_market"] = False
            df["close_long_market"] = False
            df["open_short_market"] = False
            df["close_short_market"] = False
            df["pair"] = pair
            df["null"] = np.nan
            
            if self.use_long:
                # -- Populate open long market --
                df.loc[
                    (df['n1_close'] < df['n1_higher_band']) 
                    & (df['close'] > df['higher_band']) 
                    & (df["close"] > df["long_ma"]) 
                    , "open_long_market"
                ] = True
            
                # -- Populate close long market --
                df.loc[
                    (df['close'] < df['ma_band']) 
                    , "close_long_market"
                ] = True

            if self.use_short:
                # -- Populate open short market --
                df.loc[
                    (df['n1_close'] > df['n1_lower_band']) 
                    & (df['close'] < df['lower_band']) 
                    & (df["close"] < df["long_ma"])
                    , "open_short_market"
                ] = True
            
                # -- Populate close short market --
                df.loc[
                    (df['close'] > df['ma_band']) 
                    , "close_short_market"
                ] = True
                
            # -- Populate pair list per date (do not touch)--
            data_open_long.append(
                df.loc[
                (df['open_long_market']  == True) 
                ]['pair']
            )
            data_close_long.append(
                df.loc[
                (df['close_long_market']  == True) 
                ]['pair']
            )
            data_open_short.append(
                df.loc[
                (df['open_short_market']  == True) 
                ]['pair']
            )
            data_close_short.append(
                df.loc[
                (df['close_short_market']  == True) 
                ]['pair']
            )

        data_open_long.append(self.df_list[self.oldest_pair]['null'])
        data_close_long.append(self.df_list[self.oldest_pair]['null'])
        data_open_short.append(self.df_list[self.oldest_pair]['null'])
        data_close_short.append(self.df_list[self.oldest_pair]['null'])
        df_open_long = pd.concat(data_open_long, axis=1)
        df_open_long['combined']= df_open_long.values.tolist()
        df_open_long['combined'] = [[i for i in j if i == i] for j in list(df_open_long['combined'])]
        df_close_long = pd.concat(data_close_long, axis=1)
        df_close_long['combined']= df_close_long.values.tolist()
        df_close_long['combined'] = [[i for i in j if i == i] for j in list(df_close_long['combined'])]
        df_open_short = pd.concat(data_open_short, axis=1)
        df_open_short['combined']= df_open_short.values.tolist()
        df_open_short['combined'] = [[i for i in j if i == i] for j in list(df_open_short['combined'])]
        df_close_short = pd.concat(data_close_short, axis=1)
        df_close_short['combined']= df_close_short.values.tolist()
        df_close_short['combined'] = [[i for i in j if i == i] for j in list(df_close_short['combined'])]
        self.open_long_obj = df_open_long['combined']
        self.close_long_obj = df_close_long['combined']
        self.open_short_obj = df_open_short['combined']
        self.close_short_obj = df_close_short['combined']
        
        # -- Log --
        if(show_log):
            print("Open LONG length on oldest pair :",len(self.df_list[self.oldest_pair].loc[self.df_list[self.oldest_pair]["open_long_market"]==True]))
            print("Close LONG length on oldest pair :",len(self.df_list[self.oldest_pair].loc[self.df_list[self.oldest_pair]["close_long_market"]==True]))
            print("Open SHORT length on oldest pair :",len(self.df_list[self.oldest_pair].loc[self.df_list[self.oldest_pair]["open_short_market"]==True]))
            print("Close SHORT length on oldest pair :",len(self.df_list[self.oldest_pair].loc[self.df_list[self.oldest_pair]["close_short_market"]==True]))
        
        return self.df_list[self.oldest_pair]
    
    def run_backtest(self, initial_wallet=1000, leverage=1, max_var=1, maker_fee=0, taker_fee=0.0007):
        df_ini = self.df_list[self.oldest_pair][:]
        wallet = initial_wallet
        usd_remaining = initial_wallet
        long_exposition = 0
        short_exposition = 0
        trades = []
        days = []
        current_day = 0
        previous_day = 0
        current_positions = {}
        positions_exposition = {}
        for pair in self.df_list:
            positions_exposition[pair] = {"long":0, "short":0}
        var = ValueAtRisk(df_list=self.df_list.copy())
        var_counter = 0
        
        for index, row in df_ini.iterrows():
            if max_var != 0:
                if var_counter == 0:
                    var.update_cov(current_date=index, occurance_data=1000)
                    var_counter = 1000
                else:
                    var_counter -= 1
            # -- Add daily report --
            current_day = index.day
            if previous_day != current_day:
                temp_wallet = wallet
                for pos in current_positions:
                    actual_row = self.df_list[pos].loc[index]
                    if current_positions[pos]['side'] == "LONG":
                        close_price = actual_row['close']
                        trade_result = (close_price - current_positions[pos]['price']) / current_positions[pos]['price']
                        close_size = current_positions[pos]['size'] + current_positions[pos]['size']  * trade_result
                        fee = close_size * taker_fee
                        temp_wallet += close_size - current_positions[pos]['size'] - fee
                    elif current_positions[pos]['side'] == "SHORT":
                        close_price = actual_row['close']
                        trade_result = (current_positions[pos]['price'] - close_price) / current_positions[pos]['price']
                        close_size = current_positions[pos]['size'] + current_positions[pos]['size']  * trade_result
                        fee = close_size * taker_fee
                        temp_wallet += close_size - current_positions[pos]['size'] - fee
                if max_var != 0:
                    risk = var.get_var(positions=positions_exposition)
                else:
                    risk = 0
                # if risk == 0 and long_exposition + short_exposition > 0.1:
                #     print(positions_exposition)
                # elif math.isnan(risk):
                #     print(positions_exposition)
                days.append({
                    "day":str(index.year)+"-"+str(index.month)+"-"+str(index.day),
                    "wallet":temp_wallet,
                    "price":row['close'],
                    "long_exposition":long_exposition,
                    "short_exposition":short_exposition,
                    "risk": risk
                })
            
            previous_day = current_day 
            
            # Sell
            close_long_row = self.close_long_obj.loc[index]
            close_short_row = self.close_short_obj.loc[index]
            if len(current_positions) > 0:
                position_to_close = set({k: v for k,v in current_positions.items() if v['side'] == "LONG"}).intersection(set(close_long_row))
                for pos in position_to_close:
                    actual_row = self.df_list[pos].loc[index]
                    close_price = actual_row['close']
                    trade_result = (close_price - current_positions[pos]['price']) / current_positions[pos]['price']
                    close_size = current_positions[pos]['size'] + current_positions[pos]['size']  * trade_result
                    fee = close_size * taker_fee
                    wallet += close_size - current_positions[pos]['size'] - fee
                    long_exposition -= self.parameters_obj[pos]['wallet_exposure']
                    positions_exposition[pos]["long"] -= self.parameters_obj[pos]['wallet_exposure']
                    trades.append({
                        "pair": pos,
                        "open_date": current_positions[pos]['date'],
                        "close_date": index,
                        "position": current_positions[pos]['side'],
                        "open_reason": current_positions[pos]['reason'],
                        "close_reason": "Limit",
                        "open_price": current_positions[pos]['price'],
                        "close_price": close_price,
                        "open_fee": current_positions[pos]['fee'],
                        "close_fee": fee,
                        "open_trade_size":current_positions[pos]['size'],
                        "close_trade_size":close_size,
                        "wallet": wallet,
                    })
                    del current_positions[pos]   
                short_position_to_close = set({k: v for k,v in current_positions.items() if v['side'] == "SHORT"}).intersection(set(close_short_row))
                for pos in short_position_to_close:
                    actual_row = self.df_list[pos].loc[index]
                    close_price = actual_row['close']
                    trade_result = (current_positions[pos]['price'] - close_price) / current_positions[pos]['price']
                    close_size = current_positions[pos]['size'] + current_positions[pos]['size'] * trade_result
                    fee = close_size * taker_fee
                    wallet += close_size - current_positions[pos]['size'] - fee
                    short_exposition -= self.parameters_obj[pos]['wallet_exposure']
                    positions_exposition[pos]["short"] -= self.parameters_obj[pos]['wallet_exposure']
                    trades.append({
                        "pair": pos,
                        "open_date": current_positions[pos]['date'],
                        "close_date": index,
                        "position": current_positions[pos]['side'],
                        "open_reason": current_positions[pos]['reason'],
                        "close_reason": "Limit",
                        "open_price": current_positions[pos]['price'],
                        "close_price": close_price,
                        "open_fee": current_positions[pos]['fee'],
                        "close_fee": fee,
                        "open_trade_size":current_positions[pos]['size'],
                        "close_trade_size":close_size,
                        "wallet": wallet,
                    })
                    del current_positions[pos] 
                    
            # Buy
            open_long_row = self.open_long_obj.loc[index]
            if len(open_long_row) > 0:
                for pos in open_long_row:
                    # if (pos not in current_positions) and (long_exposition + self.parameters_obj[pos]['wallet_exposure'] <= 1) and (long_exposition + self.parameters_obj[pos]['wallet_exposure'] - short_exposition <= max_side_exposition):
                    if (pos not in current_positions) and (long_exposition + self.parameters_obj[pos]['wallet_exposure'] <= 1):
                        if max_var != 0:
                            new_positions = copy.deepcopy(positions_exposition)
                            new_positions[pos]["long"] += self.parameters_obj[pos]['wallet_exposure']
                            new_risk = var.get_var(positions=new_positions)
                            if new_risk > max_var:
                                continue
                        actual_row = self.df_list[pos].loc[index]
                        open_price = actual_row['close']
                        pos_size = wallet * self.parameters_obj[pos]['wallet_exposure'] * leverage
                        long_exposition += self.parameters_obj[pos]['wallet_exposure']
                        positions_exposition[pos]["long"] += self.parameters_obj[pos]['wallet_exposure']
                        # print(positions_exposition)
                        fee = pos_size * taker_fee
                        pos_size -= fee
                        wallet -= fee
                        current_positions[pos] = {
                            "size": pos_size,
                            "date": index,
                            "price": open_price,
                            "fee":fee,
                            "reason": "Limit",
                            "side": "LONG"
                        }
            open_short_row = self.open_short_obj.loc[index]
            if len(open_short_row) > 0:
                for pos in open_short_row:
                    if (pos not in current_positions) and (short_exposition + self.parameters_obj[pos]['wallet_exposure'] <= 1):
                        if max_var != 0:
                            new_positions = copy.deepcopy(positions_exposition)
                            new_positions[pos]["short"] += self.parameters_obj[pos]['wallet_exposure']
                            new_risk = var.get_var(positions=new_positions)
                            if new_risk > max_var:
                                continue
                        actual_row = self.df_list[pos].loc[index]
                        open_price = actual_row['close']
                        pos_size = wallet * self.parameters_obj[pos]['wallet_exposure'] * leverage
                        short_exposition += self.parameters_obj[pos]['wallet_exposure']
                        positions_exposition[pos]["short"] += self.parameters_obj[pos]['wallet_exposure']
                        fee = pos_size * taker_fee
                        pos_size -= fee
                        wallet -= fee
                        current_positions[pos] = {
                            "size": pos_size,
                            "date": index,
                            "price": open_price,
                            "fee":fee,
                            "reason": "Limit",
                            "side": "SHORT"
                        }
        df_days = pd.DataFrame(days)
        df_days['day'] = pd.to_datetime(df_days['day'])
        df_days = df_days.set_index(df_days['day'])

        if len(trades) == 0:
            print("No trades")
            return None
        df_trades = pd.DataFrame(trades)
        df_trades['open_date'] = pd.to_datetime(df_trades['open_date'])
        df_trades = df_trades.set_index(df_trades['open_date'])   
        
        return get_metrics(df_trades, df_days) | {
            "wallet": wallet,
            "trades": df_trades,
            "days": df_days
        } 