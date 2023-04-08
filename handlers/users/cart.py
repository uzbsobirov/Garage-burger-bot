from aiogram import types
from loader import dp, db, bot
from aiogram.dispatcher.storage import FSMContext
from keyboards.default.menu import cart_products_markup, main_menu,cats_markup,phone,location,cancel
from states.main import ShopState
from geopy.geocoders import Nominatim
from utils.misc.product import Product
from data.config import ADMINS
from data.shipping import *


@dp.message_handler(text="Cart 🛒", state="*")
async def get_cart_items(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    cart_id = db.select_cart(user_id=user_id)[0]
    items = db.get_all_items(cart_id=cart_id)
    if items:
        msg = "«❌ Product» - remove product from Cart\n«🗑 Clear  - Clear Cart\n\n<i>Products in Cart:</i>\n\n"
        total_price = 0
        for item in items:
            data = db.get_product_data(id=item[0])
            price = data[-2] * item[1]
            msg += f"<b>{data[1]}</b>\n<code>{data[-2]} x {item[1]} = {price} $</code>\n"
            total_price += price
        msg += f"\n\n<i>All:</i> <b>{total_price} $</b>"  
        await message.answer(msg, reply_markup=cart_products_markup(items))
        await ShopState.cart.set()
    else:
        await message.answer("Cart is empty, please order 😉")

@dp.message_handler(text="Clear 🗑", state=ShopState.cart)
async def clear_user_cart(message: types.Message, state: FSMContext):
     user_id = message.from_user.id
     cart_id = db.select_cart(user_id=user_id)[0]
     db.delete_user_cart_items(cart_id=cart_id)
     await message.answer("Successfully removed😌", reply_markup=main_menu)
     await state.finish()

@dp.message_handler(text="Order 🚚", state=ShopState.cart)
async def save_delivery_type(message: types.Message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(phone)
    markup.add(cancel)
    await message.answer("Send your phone number:", reply_markup=markup)

@dp.message_handler(content_types=["contact"], state=ShopState.cart)
async def get_user_phone_number(message: types.Message, state: FSMContext):
    await state.update_data({
        "phone": message.contact.phone_number
    })
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(location)
    markup.add(cancel)
    await message.answer("Send your location:", reply_markup=markup)

@dp.message_handler(content_types=["location"], state=ShopState.cart)
async def get_user_location(message: types.Message, state: FSMContext):
    lat = message.location.latitude
    lon = message.location.longitude
    data = await state.get_data()
    phone = data.get("phone")
    geoLoc = Nominatim(user_agent="GetLoc")
    locname = geoLoc.reverse(f"{lat}, {lon}")
    address = locname.address
    await state.update_data({"lat": lat, "lon": lon})
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton(text="✅Confirm✅"))
    markup.add(cancel)
    await message.answer(f"Confirm that your order information is correct\n\nPhone number: {phone}\nAddres: {address}", reply_markup=markup)


@dp.message_handler(text="❌Cancel❌", state=ShopState.cart)
async def cancel_order(message: types.Message, state: FSMContext):
    await message.answer("Cancel Order", reply_markup=main_menu)
    await state.finish() 

@dp.message_handler(text="✅Confirm✅", state=ShopState.cart)
async def save_order(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lat = data.get("lat")
    lon = data.get("lon")
    user_id = message.from_user.id
    cart_id = db.select_cart(user_id=user_id)[0]
    items = db.get_all_items(cart_id=cart_id)
    total_price = 0
    msg = ""
    prices = []
    for item in items:
        data = db.get_product_data(id=item[0])
        price = data[-2] * item[1]
        msg += f"{data[1]}({data[-2]}) x {item[1]} = {price} $,"
        prices.append(
            types.LabeledPrice(label=data[1], amount=int(price * 100))
        )
        total_price += price    
    db.add_order(user_id=user_id, total_price=total_price, lat=lat, lon=lon)        
    prices.append( 
        LabeledPrice(
            label='Yetkazib berish (7 kun)',
            amount=2,# 20 000.00 so'm
        )
    )
    msg += f"Yetkazib berish (7 kun) - 2 $"

    products = Product(
        title="Buyurtmangiz uchun to'lov qiling",
        description=msg,
        start_parameter="create_invoice_order",
        currency="UZS",
        prices=prices,
        need_email=True,
        need_name=True,
        need_phone_number=True,
        need_shipping_address=True, # foydalanuvchi manzilini kiritishi shart
        is_flexible=True
    )

    await bot.send_invoice(chat_id=message.from_user.id, **products.generate_invoice(),payload=f"payload:order_user_id{user_id}")
    
    db.delete_user_cart_items(cart_id=cart_id)
    await state.finish()
@dp.shipping_query_handler()
async def choose_shipping(query: types.ShippingQuery):
    if query.shipping_address.country_code != "UZ":
        await bot.answer_shipping_query(shipping_query_id=query.id,
                                        ok=False,
                                        error_message="We cannot deliver abroad")
    elif query.shipping_address.city.lower() == "urganch":
        await bot.answer_shipping_query(shipping_query_id=query.id,
                                        shipping_options=[FAST_SHIPPING, REGULAR_SHIPPING, PICKUP_SHIPPING],
                                        ok=True)
    else:
        await bot.answer_shipping_query(shipping_query_id=query.id,
                                        shipping_options=[REGULAR_SHIPPING],
                                        ok=True)

@dp.pre_checkout_query_handler()
async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query_id=pre_checkout_query.id,
                                        ok=True)
    await bot.send_message(chat_id=pre_checkout_query.from_user.id,
                           text="Thank you for your purchase!",reply_markup=main_menu)
    await bot.send_message(chat_id=ADMINS[0],
                           text=f"The following product was sold: {pre_checkout_query.invoice_payload}\n"
                                f"ID: {pre_checkout_query.id}\n"
                                f"Telegram user: {pre_checkout_query.from_user.first_name}\n"
                                f"Xaridor: {pre_checkout_query.order_info.name}, tel: {pre_checkout_query.order_info.phone_number}")

    
@dp.message_handler(state=ShopState.cart)
async def delete_product(message: types.Message):
    user_id = message.from_user.id
    cart_id = db.select_cart(user_id=user_id)[0]
    product = message.text[2:-2]
    product_id = db.get_product_data(name=product)[0]
    db.delete_product_user_cart(product_id=product_id, cart_id=cart_id)

    items = db.get_all_items(cart_id=cart_id)
    if items:
        msg = "<i>Product in Cart:</i>\n\n"
        total_price = 0
        for item in items:
            data = db.get_product_data(id=item[0])
            price = data[-2] * item[1]
            msg += f"<b>{data[1]}</b>\n<code>{data[-2]} x {item[1]} = {price} $</code>\n"
            total_price += price
        msg += f"\n\n<i>All:</i> <b>{total_price} $</b>"  
        await message.answer(msg, reply_markup=cart_products_markup(items))
        await ShopState.cart.set()
    else:
         await message.answer("You've emptied your shopping cart 😌, I'll help you pack it", reply_markup=cats_markup)
         await ShopState.category.set()