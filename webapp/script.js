document.addEventListener('DOMContentLoaded', () => {
    const tg = window.Telegram.WebApp;
    tg.ready();
    tg.expand();

    const catalogContainer = document.getElementById('catalog-container');
    const modal = document.getElementById('gallery-modal');
    const modalImage = document.getElementById('gallery-image');
    const modalCounter = document.getElementById('gallery-counter');
    const closeModalBtn = document.querySelector('.close-btn');
    const prevBtn = document.querySelector('.prev-btn');
    const nextBtn = document.querySelector('.next-btn');

    let allProducts = {}; // Хранилище всех товаров по ID для быстрого доступа
    let currentGalleryImages = [];
    let currentImageIndex = 0;
    let cart = {}; // Наша корзина { productId: quantity }

    // --- 1. Загрузка товаров с сервера ---
    async function fetchProducts() {
        // ВАЖНО: Укажите здесь ПОЛНЫЙ ПУБЛИЧНЫЙ АДРЕС вашего бота.
        // Этот URL должен указывать на ваш бэкенд на Render.
        const backendUrl = 'https://btdetailing.onrender.com';
        const apiUrl = `${backendUrl}/api/products`; 
        
        // Лог для отладки, чтобы видеть, куда идет запрос
        console.log(`Fetching products from: ${apiUrl}`);

        // Показываем индикатор загрузки
        catalogContainer.innerHTML = '<div class="loader"></div>';

        try {
            const response = await fetch(apiUrl);
            if (!response.ok) {
                throw new Error(`Ошибка сети: ${response.status}`);
            }
            const categories = await response.json();
            // Отрисовка каталога заменит индикатор загрузки
            renderCatalog(categories);
        } catch (error) {
            catalogContainer.innerHTML = `<div class="error-message">Не удалось загрузить товары. Попробуйте позже.</div>`;
            console.error("Ошибка при загрузке товаров:", error);
        }
    }

    // --- 2. Отрисовка каталога ---
    function renderCatalog(categories) {
        catalogContainer.innerHTML = ''; // Очищаем загрузчик
        if (!categories || categories.length === 0) {
            catalogContainer.innerHTML = '<p class="error-message">Товары не найдены.</p>';
            return;
        }

        categories.forEach(category => {
            const categoryElement = document.createElement('div');
            categoryElement.className = 'category';
            
            const categoryTitle = document.createElement('h2');
            categoryTitle.className = 'category-title';
            categoryTitle.textContent = category.name;
            categoryElement.appendChild(categoryTitle);

            category.subcategories.forEach(subcategory => {
                const subcategoryTitle = document.createElement('h3');
                subcategoryTitle.className = 'subcategory-title';
                subcategoryTitle.textContent = subcategory.name;
                categoryElement.appendChild(subcategoryTitle);

                const productsGrid = document.createElement('div');
                productsGrid.className = 'products-grid';

                subcategory.products.forEach(product => {
                    allProducts[product.id] = product; // Сохраняем товар для галереи
                    const productCard = createProductCard(product);
                    productsGrid.appendChild(productCard);
                });
                categoryElement.appendChild(productsGrid);
            });

            catalogContainer.appendChild(categoryElement);
        });
    }

    // --- 3. Создание карточки товара ---
    function createProductCard(product) {
        const card = document.createElement('div');
        card.className = 'product-card';

        const imageContainer = document.createElement('div');
        imageContainer.className = 'product-image-container';
        imageContainer.addEventListener('click', () => openGallery(product.id));
        
        const image = document.createElement('img');
        image.className = 'product-image';
        image.src = product.imageUrl || ''; // Используем imageUrl, который отдает бот
        image.alt = product.name;
        image.onerror = () => { image.src = 'https://via.placeholder.com/150'; }; // Заглушка, если фото не загрузилось
        
        imageContainer.appendChild(image);

        const info = document.createElement('div');
        info.className = 'product-info';

        const name = document.createElement('p');
        name.className = 'product-name';
        name.textContent = product.name;

        const price = document.createElement('p');
        price.className = 'product-price';
        price.textContent = `${product.price} руб.`;

        const addButton = document.createElement('button');
        addButton.className = 'add-to-cart-btn';
        addButton.textContent = 'В корзину';
        addButton.addEventListener('click', (e) => { e.stopPropagation(); addToCart(product.id); });

        info.appendChild(name);
        info.appendChild(price);
        info.appendChild(addButton);
        
        card.appendChild(imageContainer);
        card.appendChild(info);

        return card;
    }

    // --- 4. Логика галереи ---
    function openGallery(productId) {
        const product = allProducts[productId];
        if (!product) return;

        // Собираем все фото: главное + детальные
        currentGalleryImages = [product.imageUrl, ...(product.detailImages || [])].filter(Boolean);
        if (currentGalleryImages.length === 0) return;

        currentImageIndex = 0;
        updateGalleryView();
        modal.style.display = 'flex';
    }

    function closeGallery() { modal.style.display = 'none'; }

    function updateGalleryView() {
        modalImage.src = currentGalleryImages[currentImageIndex];
        modalCounter.textContent = `${currentImageIndex + 1} / ${currentGalleryImages.length}`;
        prevBtn.style.display = currentGalleryImages.length > 1 ? 'block' : 'none';
        nextBtn.style.display = currentGalleryImages.length > 1 ? 'block' : 'none';
    }

    function showNextImage() { currentImageIndex = (currentImageIndex + 1) % currentGalleryImages.length; updateGalleryView(); }
    function showPrevImage() { currentImageIndex = (currentImageIndex - 1 + currentGalleryImages.length) % currentGalleryImages.length; updateGalleryView(); }

    // --- 5. Логика корзины ---
    function addToCart(productId) {
        if (cart[productId]) {
            cart[productId]++;
        } else {
            cart[productId] = 1;
        }
        tg.HapticFeedback.impactOccurred('light');
        updateMainButton();
    }

    function calculateTotalPrice() {
        let total = 0;
        for (const productId in cart) {
            total += allProducts[productId].price * cart[productId];
        }
        return total;
    }

    function updateMainButton() {
        const totalPrice = calculateTotalPrice();
        if (totalPrice > 0) {
            tg.MainButton.setText(`Оформить заказ на ${totalPrice} руб.`);
            tg.MainButton.show();
        } else {
            tg.MainButton.hide();
        }
    }

    // Обработчик нажатия на главную кнопку
    tg.onEvent('mainButtonClicked', () => {
        const dataToSend = {
            action: 'checkout',
            cart: cart
        };
        tg.sendData(JSON.stringify(dataToSend));
    });

    // --- Навешиваем обработчики событий ---
    closeModalBtn.addEventListener('click', closeGallery);
    nextBtn.addEventListener('click', showNextImage);
    prevBtn.addEventListener('click', showPrevImage);

    // --- Запускаем загрузку ---
    fetchProducts();
});
