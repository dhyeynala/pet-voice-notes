// public/firebase-config.js
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";

const firebaseConfig = {
  apiKey: "AIzaSyCVvGsrYlf8rwKVaPlQif8ipW3ghDhBv38",
  authDomain: "puppypages-29427.firebaseapp.com",
  databaseURL: "https://puppypages-29427-default-rtdb.firebaseio.com",
  projectId: "puppypages-29427",
  storageBucket: "puppypages-29427.appspot.com",
  messagingSenderId: "168138704553",
  appId: "1:168138704553:web:69353f37163a17fc1b4bb8",
  measurementId: "G-5X3SX0RBLK"
};

export const app = initializeApp(firebaseConfig);
