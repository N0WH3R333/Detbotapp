// Инициализируем WebApp
const tg = window.Telegram.WebApp;

// --- Данные о товарах ---
const products = {
    shampoo_500: { name: "Супер-шампунь для авто", price: 500 },
    microfiber_250: { name: "Волшебная микрофибра", price: 250 },
};

// --- Корзина ---
let cart = {};

// --- Функция для обновления вида корзины ---
function updateCartView() {
    const cartItemsContainer = document.getElementById('cart-items');
    const totalPriceContainer = document.getElementById('total-price-container');
    const promoContainer = document.getElementById('promo-container');
    const totalPriceSpan = document.getElementById('total-price');
    let total = 0;

    cartItemsContainer.innerHTML = ''; // Очищаем старое содержимое

    const items = Object.keys(cart);

    if (items.length === 0) {
        cartItemsContainer.innerHTML = '<p>Корзина пуста</p>';
        totalPriceContainer.style.display = 'none';
        promoContainer.style.display = 'none';
        tg.MainButton.hide(); // Скрываем главную кнопку, если корзина пуста
        return;
    }

    items.forEach(itemId => {
        const product = products[itemId];
        const quantity = cart[itemId];
        total += product.price * quantity;

        const itemRow = document.createElement('div');
        itemRow.className = 'cart-item-row';

        const textSpan = document.createElement('span');
        textSpan.innerText = `${product.name} x ${quantity} — ${product.price * quantity} руб.`;

        const removeBtn = document.createElement('button');
        removeBtn.innerText = 'Удалить';
        removeBtn.className = 'remove-btn';
        removeBtn.onclick = () => removeFromCart(itemId);

        itemRow.appendChild(textSpan);
        itemRow.appendChild(removeBtn);
        cartItemsContainer.appendChild(itemRow);
    });

    totalPriceSpan.innerText = total;
    totalPriceContainer.style.display = 'block';
    promoContainer.style.display = 'block';

    // Показываем и настраиваем главную кнопку
    tg.MainButton.setText(`Оформить заказ на ${total} руб.`);
    tg.MainButton.show();
}

// --- Функция добавления в корзину ---
function addToCart(itemId) {
    if (cart[itemId]) {
        cart[itemId]++;
    } else {
        cart[itemId] = 1;
    }
    updateCartView();
}

// --- Функция удаления из корзины ---
function removeFromCart(itemId) {
    if (cart[itemId]) {
        cart[itemId]--; // Уменьшаем количество
        if (cart[itemId] <= 0) {
            delete cart[itemId]; // Если количество 0, удаляем товар из корзины
        }
    }
    updateCartView();
}

// --- Инициализация WebApp ---
document.addEventListener('DOMContentLoaded', () => {
    tg.ready(); // Сообщаем Telegram, что WebApp готов
    tg.expand(); // Расширяем на весь экран

    // Отображаем имя пользователя
    const user = tg.initDataUnsafe.user;
    if (user && user.first_name) {
        document.getElementById('user-name').innerText = user.first_name;
    }

    // Навешиваем обработчики на кнопки "Добавить в корзину"
    document.getElementById('add_shampoo').addEventListener('click', () => addToCart('shampoo_500'));
    document.getElementById('add_microfiber').addEventListener('click', () => addToCart('microfiber_250'));

    // Обработчик для главной кнопки Telegram
    tg.MainButton.onClick(() => {
        const promocode = document.getElementById('promocode-input').value;
        // При клике отправляем данные корзины в бот
        tg.sendData(JSON.stringify({
            action: 'checkout',
            cart: cart,
            promocode: promocode
        }));
    });

    updateCartView(); // Первоначальное отображение корзины
});